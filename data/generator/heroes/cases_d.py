from heroes.catalog_cases import build_case
def build(ctx):
    for c in ("C12","C13","C14","C15"): build_case(ctx,c)
