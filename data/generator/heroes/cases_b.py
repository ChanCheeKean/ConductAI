from heroes.catalog_cases import build_case
def build(ctx):
    for c in ("C05","C06","C07","C07b","C08","C09"): build_case(ctx,c)
