# 국제 표준 기반 하이브리드 파일 온톨로지 설계

## 목적

`semantic-data-portal`에 파일의 의미 정체성과 물리 저장 위치를 분리하는 상위 카탈로그를 추가한다. 사용자는 파일이 로컬 디스크, Synology 동기화 폴더, AWS S3, S3 호환 저장소, Azure Blob 중 어디에 있든 프로젝트·시스템·업무 단계·산출물 종류·주제로 검색하고 실제 위치를 찾을 수 있어야 한다.

포털은 naruon 문서 지식 그래프 위의 카탈로그·거버넌스 계층이라는 기존 경계를 유지한다. 원문과 원문 조각은 파일을 읽고 LLM에 보내는 동안에만 사용하며 포털 그래프나 GitHub에는 저장하지 않는다.

## 승인된 범위

- 기존 Apache AGE 그래프와 pgvector 의미 검색을 재사용한다.
- 파일 내용은 로컬에서 추출하며, 사용자가 승인한 최소 원문 조각만 `contextual-orchestrator`의 LLM 호환 API로 전송한다. 포털은 OpenAI를 직접 호출하지 않는다.
- 파일을 이동·삭제·복사하지 않는다. 수집은 읽기 전용이다.
- Synology는 필수 기반시설이 아니라 `filesystem` 저장소의 한 배치 형태다.
- 저장소 공급자는 `filesystem`, `s3`, `s3_compatible`, `azure_blob`을 지원한다.
- 공급자 자격증명과 OpenAI API key는 `contextual-orchestrator`의 credential registry 경계 안에만 둔다. 포털은 orchestrator inference token만 주입받으며 어떤 자격증명도 그래프·문서·로그·GitHub에 저장하지 않는다.
- LLM 결과는 근거 조각, 신뢰도, `proposed` 검토 상태를 가진 후보 주장으로 저장한다. LLM이 온톨로지의 정답을 직접 확정하지 않는다.
- OCR, HWP, legacy DOC/XLS 파서는 1차 파일럿에 포함하지 않는다. 실제 12개 파일은 PDF, DOCX, PPTX, XLSX로 구성되어 있다.

## 국제 표준 프로파일

애플리케이션 프로파일 이름은 `CWL File Knowledge Profile 0.1`로 한다.

| 목적 | 표준 | 적용 |
|---|---|---|
| 공통 그래프 모델 | RDF 1.1 | JSON-LD 및 Turtle 용어의 기준 모델 |
| 업무 개념과 제약 | OWL 2 | CWL 클래스와 객체 속성 정의 |
| 통제 어휘·동의어 | SKOS | 프로젝트, 시스템, 단계, 산출물, 주제 후보 |
| 구조 검증 | SHACL 1.0 | 파일 자산·배포 위치·근거 주장 shape |
| 카탈로그·배포·버전 | DCAT 3 | `dcat:Resource`, `dcat:Distribution`, 버전 관계 |
| 문서 메타데이터 | DCMI Terms | 제목, 형식, 생성·수정 시각, 식별자, 주제 |
| 출처·파생 관계 | PROV-O | `prov:Entity`, `prov:wasDerivedFrom`, 생성 근거 |
| 체크섬 | SPDX terms | SHA-256 checksum 표현 |
| 교환 | JSON-LD 1.1 | 포털 API의 표준 내보내기 |
| 외부 질의 호환 | SPARQL 1.1 | 내보낸 RDF를 표준 RDF store에서 질의 가능 |

RDF 1.2와 SHACL 1.2는 2026-07-21 현재 안정된 Recommendation 기준선이 아니므로 채택하지 않고 향후 호환 대상으로만 추적한다. ISO/IEC 11179는 초기 파일 발견에 필요한 범위를 넘는 메타데이터 등록소 운영 부담이 있어 1차 범위에서 제외한다.

## 핵심 모델

### FileAsset

콘텐츠 SHA-256으로 식별되는 의미 자산이다. 하나의 파일이 이름이나 저장소만 달리해 복제되어도 같은 `FileAsset`이다.

- RDF type: `cwl:FileAsset`, `dcat:Resource`, `prov:Entity`
- 필수 값: SHA-256, 제목, media type, byte size
- 선택 값: 생성·수정 시각, 이전 버전, 파생 원본
- 그래프 node kind: `file_asset`
- node id: `urn:sha256:<64 lowercase hex>`

### Distribution

`FileAsset`의 물리적 접근 위치다. 한 자산은 0개 이상의 `dcat:Distribution`을 가진다.

- 공급자: `filesystem`, `s3`, `s3_compatible`, `azure_blob`
- 공통 값: locator IRI, endpoint id, availability, ETag, version id, checksum
- 공급자 값: bucket 또는 container, object key/blob name
- Synology 경로는 별도 공급자 타입을 만들지 않고 `filesystem` distribution으로 기록한다.
- 기본 JSON-LD 응답은 locator를 숨긴다. 명시적으로 요청하고 정책 검사를 통과한 경우에만 실제 위치를 포함한다.

### SemanticAssertion

LLM 또는 규칙이 제안한 파일과 업무 개념 사이의 관계다.

- 허용 관계: `belongsToProject`, `usesSystem`, `hasWorkPhase`, `hasArtifactType`, `hasTopic`, `wasDerivedFrom`, `previousVersion`
- 필수 값: 대상 개념, 근거 참조(chunk SHA-256과 문자 offset), 신뢰도(0..1), 추출 방법, 검토 상태
- 모든 LLM 주장의 초기 상태는 `proposed`다.
- SHACL 호환 검증은 필수 필드·관계 allowlist·신뢰도 범위·근거 참조 존재를 검사한다.
- 주장은 그래프 탐색과 검색에 사용하되 응답에 검토 상태를 항상 노출한다.

## 저장소 어댑터

핵심 수집기는 다음 세 연산만 요구한다.

1. `list(prefix)` — 후보 object를 열거한다.
2. `stat(object)` — 크기, 수정 시각, ETag/version을 조회한다.
3. `read(object, max_bytes)` — 제한된 크기로 원문 bytes를 읽는다.

구현은 다음과 같다.

- `FilesystemReader`: `pathlib`로 로컬, UNC, Synology 동기화 폴더를 읽는다.
- `S3Reader`: 호출자가 주입한 boto3 호환 client를 사용한다. 사용자 지정 endpoint를 준 client면 S3 호환 저장소도 같은 구현을 쓴다.
- `AzureBlobReader`: 호출자가 주입한 Azure `ContainerClient` 호환 객체를 사용한다.

SDK를 포털의 필수 의존성으로 추가하지 않는다. 실제 클라우드 배포 환경이 이미 사용하는 SDK client를 주입하며, CI는 같은 public method를 가진 fake client로 계약을 검증한다.

## 문서 추출과 LLM 흐름

1. reader가 bytes와 저장소 메타데이터를 반환한다.
2. SHA-256을 계산해 `FileAsset`을 결정하고 중복 위치를 합친다.
3. DOCX/PPTX/XLSX는 Python 표준 `zipfile`·XML parser로 텍스트를 추출한다.
4. PDF는 `pypdf`로 텍스트를 추출한다. 이미지 전용 PDF는 `needs_ocr`로 보고하고 전송하지 않는다.
5. 텍스트를 고정 크기 조각으로 나누고 파일당 최대 전송 문자 수를 적용한다.
6. `contextual-orchestrator`의 `POST /v1/chat/completions`에 `response_format=json_schema`, `store=false`를 보내 의미 후보와 짧은 근거 인용을 받는다. orchestrator가 provider와 OpenAI 자격증명을 소유한다.
7. 근거 인용이 입력 조각에 실제로 존재하는지 확인한 뒤 인용문 대신 chunk SHA-256과 문자 offset만 남긴다.
8. 여러 조각의 후보를 `(관계, 정규화 label)` 기준으로 합치고 가장 높은 신뢰도와 그 근거 참조를 유지한다.
9. SHACL 호환 검증을 통과한 후보만 그래프에 `proposed` assertion으로 기록한다.
10. 파일 node의 embedding text는 제목과 제안된 개념 label만 사용하고 `contextual-orchestrator`의 동기 `POST /v1/embeddings`로 벡터화한다. 원문과 근거 인용문은 저장하지 않는다.

포털에는 orchestrator base URL과 model id를 KV application config로, inference token을 주입된 credential registry로 공급한다. 포털 코드가 OpenAI key나 `os.getenv()`를 읽지 않는다. HTTP transport는 Python 표준 라이브러리를 사용하고 LLM 요청에 `store: false`와 pinned model id를 포함한다. orchestrator의 동기 embedding endpoint는 기존 `/v1/batch/embeddings` 코어의 분할·provider backend·비용 원장을 재사용하고 최대 30초 동안 완료를 기다린 뒤 OpenAI 호환 응답을 반환한다. CI에서는 양쪽 HTTP 호출을 fake transport로 대체한다.

## API와 정책

- `POST /file-assets`: 관리자만 검증된 파일 메타데이터와 후보 주장을 ingest한다.
- `GET /file-assets/{asset_id}`: 인증된 reader가 자산과 의미 관계를 조회한다.
- `GET /file-assets/{asset_id}/jsonld`: 기본적으로 저장소 locator를 제거한 JSON-LD를 반환한다.
- `GET /file-assets/{asset_id}/validate`: SHACL 호환 validation report를 반환한다.
- 기존 `POST /graph/query`와 `POST /search/semantic`을 그대로 사용해 관계 탐색과 의미 검색을 제공한다.

모든 write/read route는 기존 `policy.evaluate()` 경로를 재사용한다. 원문 조각, API key, cloud credential은 request/response, graph property, audit detail에 포함하지 않는다.

## 효성중공업 VOC 파일럿

초기 root는 다음 로컬 동기화 폴더다.

`D:\SynologyDrive\업무자료\Download_정리_2026-07-15\01_문서`

파일명에 `효성중공업` 또는 `중공업VOC`가 포함된 최상위 파일 12개를 읽기 전용으로 수집한다.

- DOCX 4개
- XLSX 4개
- PPTX 2개
- PDF 2개
- SHA-256 기준 고유 `FileAsset` 10개
- 같은 SHA-256을 가진 XLSX 3개는 자산 하나와 distribution 세 개로 모델링한다.

실제 파일명, locator, 추출 원문, LLM 응답 전문은 GitHub에 commit하지 않는다. 파일럿 결과는 사용자 로컬의 Git 제외 경로에 JSON-LD/요약 manifest로 저장한다.

## 실패와 안전 동작

- 허용 root 밖 path, 상위 경로 탈출, symlink/reparse point는 읽지 않는다.
- 파일 크기 제한을 넘으면 `too_large`로 기록하고 읽지 않는다.
- 지원하지 않는 형식은 `unsupported_format`, 추출 문자가 없으면 `needs_ocr`로 기록한다.
- API timeout, rate limit, 불완전 응답은 해당 파일을 `extraction_failed`로 남기며 기존 그래프를 덮어쓰지 않는다.
- storage credential 또는 orchestrator inference token이 없으면 fail closed 한다. OpenAI key는 포털에 존재하지 않는다.
- 쓰기·삭제·이동·원격 object mutation 기능은 구현하지 않는다.

## 검증 기준

- 같은 bytes의 서로 다른 locator가 한 `FileAsset`으로 합쳐진다.
- 각 공급자 reader가 list/stat/read 계약을 만족한다.
- 지원 문서에서 텍스트가 추출되고 원문은 graph property에 남지 않는다.
- orchestrator LLM 요청은 strict schema, `store: false`, 최소 조각만 포함하고 OpenAI 직접 URL을 사용하지 않는다.
- embedding 요청은 orchestrator의 동기 `/v1/embeddings`만 사용하며 벡터 순서·차원을 검증한다.
- 허용되지 않은 관계나 검증 가능한 근거 참조가 없는 후보는 validation에서 거부된다.
- JSON-LD가 DCAT/DCTERMS/PROV/SKOS/SPDX/CWL context와 locator redaction을 지킨다.
- 기존 전체 pytest suite와 새 단일 파일 지식 테스트가 통과한다.
- Codegraph를 동기화하고 변경 영향과 관련 테스트를 확인한다.

## 제외 사항

- 파일 이동·삭제·중복 파일 제거
- OCR 및 HWP/legacy Office parsing
- S3/Azure SDK를 필수 dependency로 추가
- cloud object 쓰기 또는 lifecycle 관리
- 자동 온톨로지 승인
- 원문·embedding의 GitHub 업로드
- `semantic-data-portal`에서 OpenAI 또는 다른 LLM provider를 직접 호출하는 경로
