from heroes.catalog_cases import build_case
def build(ctx):
    for c in ("C16","C17","C18","C19","C20"): build_case(ctx,c)
