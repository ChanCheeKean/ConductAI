from heroes.catalog_cases import build_case
def build(ctx):
    for c in ("C01","C02","C02b","C03","C04"): build_case(ctx,c)
