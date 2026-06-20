"""사용법: python -m clearhs <invoice.pdf> [<packing_list.pdf>] [<specification.pdf>]"""
import json
import sys

from .pipeline import run_pipeline

DOC_TYPE_ORDER = ["invoice", "packing_list", "specification"]


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python -m clearhs <invoice.pdf> [<packing_list.pdf>] [<specification.pdf>]")
        sys.exit(1)

    paths = sys.argv[1:]
    doc_paths = {DOC_TYPE_ORDER[i]: path for i, path in enumerate(paths) if i < len(DOC_TYPE_ORDER)}

    result = run_pipeline(doc_paths)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
