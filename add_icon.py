p = r"C:\Users\Hiranya\spy\HSM_v2.0_User_Guide.html"
svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='14' fill='#0b0f19'/><rect x='2' y='2' width='60' height='60' rx='12' fill='none' stroke='#26304a' stroke-width='2'/><path d='M10 44 C22 42 28 34 32 30 S44 18 54 16' fill='none' stroke='#4fc3f7' stroke-width='4.5' stroke-linecap='round'/><path d='M10 22 C22 26 28 30 32 30 S46 38 54 38' fill='none' stroke='#ffa726' stroke-width='4.5' stroke-linecap='round'/><circle cx='32' cy='30' r='6' fill='#00e676' stroke='#0b0f19' stroke-width='2'/></svg>"""
open(r"C:\Users\Hiranya\spy\hsm_icon.svg", "w", encoding="utf-8").write(svg.replace("'", '"'))
uri = "data:image/svg+xml," + svg.replace("<", "%3C").replace(">", "%3E").replace("#", "%23")
h = open(p, encoding="utf-8").read()
if "rel=\"icon\"" not in h:
    h = h.replace("</title>", "</title>\n<link rel=\"icon\" type=\"image/svg+xml\" href=\"" + uri + "\">", 1)
    h = h.replace("<h1>", "<h1><img src=\"" + uri + "\" alt=\"\" width=\"36\" height=\"36\" style=\"vertical-align:-7px;margin-right:10px\">", 1)
    open(p, "w", encoding="utf-8").write(h)
print(len(h), h.count(uri))
