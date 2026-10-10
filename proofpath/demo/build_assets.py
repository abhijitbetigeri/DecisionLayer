#!/usr/bin/env python3
"""Generate the offline cards and architecture diagram; no metrics needed."""
from pathlib import Path
import sys
from make_chart import render, svg
D = Path(__file__).resolve().parent

def text(s,x,y,size=32,**kw): return dict(text=s,x=x,y=y,size=size,**kw)
def box(x,y,w,h,color="ffffff"): return dict(x=x,y=y,width=w,height=h,color=color,radius=12)
def save(name,items):
    scene=dict(width=1920,height=1080,background="f7f8fa",items=items)
    target=D/name
    target.with_suffix(".svg").write_text(svg(scene))
    if "--svg-only" not in sys.argv: render(scene,target)

save("cards/title.png",[box(100,180,12,660,"2346d8"),text("DECISION LAYER",160,220,30,color="2346d8"),text("Evidence-driven enterprise\nsoftware evaluation",160,320,76,bold=True,height=240),text("Visitor Lab  +  Evaluation Workspace",160,630,36),text("A living website that demonstrates product fit.",160,740,32,color="565c69")])
save("cards/end.png",[text("Decision Layer",120,220,90,bold=True,height=140),text("Understand. Test. Compare. Decide.",120,410,46),text("github.com/abhijitbetigeri/DecisionLayer",120,620,30,color="2346d8"),text("TEAM: [ADD TEAM NAMES BEFORE SUBMISSION]",120,710,30,color="565c69"),text("Fictional products and evidence; live tests use local mock integrations.",120,910,26,color="565c69")])
items=[text("Decision Layer | Living evaluation architecture",90,55,52,bold=True),text("Presentation can change. Facts, test outcomes, and decisions remain grounded.",90,145,28,color="565c69")]
for x,title,body in [(90,"Optimization loop","Approved presentation\nExperiment > measure > refine\nCoframe-style, not integrated"),(690,"Evaluation Workspace","Brief > walkthrough > POC\nCompare > versioned report\nReview changes before approval"),(1290,"Visitor Lab","Buyer simulator\nClaim guard + deterministic oracle\nOpen-weight models on cloud")]:
    items += [box(x,300,540,370),box(x,300,540,8,"2346d8"),text(title,x+28,340,34,bold=True,width=490),text(body,x+28,435,27,width=490,height=190)]
items += [text(">",645,435,45,width=40),text(">",1245,435,45,width=40),box(200,750,1520,130,"e8edff"),text("Measured correctness and qualified evaluation outcomes feed the optimization loop",230,785,30,width=1470),text("Fictional evidence | local mock POC | cloud inference is optional and requires configuration",90,965,25,color="565c69")]
save("architecture.png",items)
