#!/usr/bin/env python3
"""Render measured Visitor Lab results, never synthetic metrics.

Usage: python3 proofpath/demo/make_chart.py [--summary PATH] [--output PATH]
Uses the actual sim_bridge summary schema and 95% Wilson intervals. Offline PNG
rendering uses macOS CoreGraphics/CoreText. Alternatively renders SVG with --svg-only.
"""
import argparse
import json
import math
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parents[2]
DEMO = Path(__file__).resolve().parent

def wilson(k, n):
    z = 1.959963984540054
    p = k / n
    den = 1 + z*z/n
    center = (p + z*z/(2*n))/den
    radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/den
    return max(0, center-radius), min(1, center+radius)

def render(scene, target):
    from render_macos import draw
    draw(scene, target)

def svg(scene):
    result = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene["width"]}" height="{scene["height"]}" viewBox="0 0 {scene["width"]} {scene["height"]}">', f'<rect width="100%" height="100%" fill="#{scene["background"]}"/>']
    for item in scene["items"]:
        if "text" in item:
            for index, line in enumerate(item["text"].splitlines()):
                size = item.get("size",32)
                result.append(f'<text x="{item["x"]}" y="{item["y"]+size+index*size*1.3}" font-family="system-ui, sans-serif" font-size="{size}" font-weight="{600 if item.get("bold") else 400}" fill="#{item.get("color","14161b")}">{escape(line)}</text>')
        else:
            result.append(f'<rect x="{item["x"]}" y="{item["y"]}" width="{item.get("width",1600)}" height="{item.get("height",100)}" rx="{item.get("radius",0)}" fill="#{item.get("color","2346d8")}"/>')
    return "\n".join(result+["</svg>"])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary",type=Path,default=ROOT/"runs/proofpath-summary.json")
    parser.add_argument("--output",type=Path,default=DEMO/"visitor-lab.png")
    parser.add_argument("--svg-only",action="store_true")
    args = parser.parse_args()
    if not args.summary.exists():
        parser.exit(2,"Results unavailable: run Visitor Lab first. No placeholder metrics rendered.\n")
    data = json.loads(args.summary.read_text())
    if data.get("stub_context"):
        parser.exit(2,"Refusing headline chart: summary uses stub context. Run the completed app.\n")
    rows = []
    for arm,label in (("A","Homepage"),("B","Evaluation Workspace")):
        r = data["results"][arm]
        n,k = r["n"],r["correct"]
        if not isinstance(n,int) or not isinstance(k,int) or not 0 <= k <= n or n <= 0:
            parser.exit(2,f"Invalid counts for arm {arm}.\n")
        rows.append((label,k/n,n,*wilson(k,n),r.get("errors",0)))
    items = [dict(text="Visitor Lab | Correct buying decisions",x=100,y=65,size=54,bold=True,height=100),dict(text="Paired simulated buyers | 95% Wilson confidence intervals",x=100,y=160,size=28,color="565c69")]
    for pct in (0,25,50,75,100):
        x=550+pct*10
        items += [dict(x=x,y=260,width=2,height=390,color="dde0e7"),dict(text=f"{pct}%",x=x-24,y=690,size=24,width=100)]
    for i,(label,rate,n,lo,hi,errors) in enumerate(rows):
        y=330+i*220
        items += [dict(text=label,x=100,y=y-15,size=30,width=430,height=90,bold=True),dict(text=f"n={n}, errors={errors}",x=100,y=y+80,size=23,color="565c69"),dict(x=550,y=y,width=rate*1000,height=54,color="2346d8",radius=4),dict(x=550+lo*1000,y=y+23,width=(hi-lo)*1000,height=8,color="14161b"),dict(x=550+lo*1000,y=y+12,width=5,height=30,color="14161b"),dict(x=550+hi*1000,y=y+12,width=5,height=30,color="14161b"),dict(text=f"{rate:.0%} [{lo:.0%}, {hi:.0%}]",x=550,y=y+65,size=27)]
    items += [dict(text=f'Experiment: {data.get("experiment","not specified")} | {data.get("created_at","date not supplied")}',x=100,y=790,size=24,color="565c69"),dict(text="Fetch-mode evaluation. Simulated buyers; not evidence of human conversion lift.",x=100,y=850,size=24,color="565c69")]
    scene=dict(width=1920,height=1080,background="f7f8fa",items=items)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.with_suffix(".svg").write_text(svg(scene))
    if not args.svg_only: render(scene,args.output)
    print(args.output.with_suffix(".svg") if args.svg_only else args.output)

if __name__ == "__main__": main()
