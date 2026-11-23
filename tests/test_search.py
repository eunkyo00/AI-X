import sys
sys.path.insert(0, "Role01")

from search_engine import search_files

queries = [
    "데이터사이언스 강의자료",
    "지난달 수정한 데이터사이언스 코드",
    "펭귄 종류를 CNN으로 분류하는 파일"
]

for query in queries:
    print("\n검색어:", query)

    results = search_files(query)

    for result in results:
        print(result["file_id"], result["filename"], round(result["score"], 4))
