# Great-Star

## 작업물 저장 위치

작업 결과물은 로컬 디스크에 남기지 않는다. 이 세션 컨테이너는 일정 시간 뒤
회수되므로, 저장하지 않은 파일은 사라진다. 완성된 결과물은 아래 세 곳 중
하나에 둔다.

| 결과물 | 저장 위치 |
| --- | --- |
| 코드, 설정 | 이 저장소 (커밋 후 push) |
| 문서, 표, 자료 파일 | Google Drive `AI 작업물` 폴더 |
| 리포트, 대시보드 등 보여주는 것 | Artifact (링크를 Drive 폴더에 메모) |

### Google Drive

- 폴더: `AI 작업물`
- 폴더 ID: `19hJFGgUSZaLQ78CoIAGO7tmCjsqDcnbS`
- https://drive.google.com/drive/folders/19hJFGgUSZaLQ78CoIAGO7tmCjsqDcnbS

Drive 커넥터의 `create_file`에 `parentId`로 위 폴더 ID를 넘겨 저장한다.
`text/plain`, `text/csv`로 올리면 각각 구글 문서·스프레드시트로 변환되어
브라우저에서 바로 열린다. 원본 형식을 유지해야 하면
`disableConversionToGoogleType: true`를 준다.

파일명은 `YYYY-MM-DD 제목` 형식으로 날짜를 앞에 붙인다.

Drive 커넥터가 연결되지 않은 세션에서는 결과물을 저장소에 커밋하고,
Drive에 옮겨야 할 파일이 무엇인지 알린다.
