from heroes.catalog_cases import build_case
def build(ctx):
    for c in ("C10","C11","C11b"): build_case(ctx,c)
