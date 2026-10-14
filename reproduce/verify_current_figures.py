"""Verify exported vector geometry, editable fonts and text-line intersections.

The supplied pdf_overlap_check.py depends on PyMuPDF, unavailable in this
runtime. This equivalent uses pdfplumber paths and word boxes, sampling every
stroked line/cubic curve. As in the supplied check, fills are ignored. Results
are conservative review candidates, not automatic declarations of errors.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from _paths import OUT
import json
import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from pypdf import PdfReader
from PIL import Image

ROOT=OUT
QA=OUT/'qa'
STEMS=['fig1_emission_rate','fig1_overview','fig_gamma_behavior','fig8_calibration']

def sampled_path(path):
    current=None; start=None; points=[]
    for item in path:
        cmd=item[0]
        if cmd=='m': current=np.array(item[1]); start=current
        elif cmd=='l' and current is not None:
            target=np.array(item[1]); count=max(12,int(np.linalg.norm(target-current))+1)
            points.extend(current+(target-current)*u for u in np.linspace(0,1,count)); current=target
        elif cmd=='c' and current is not None:
            p0,p1,p2,p3=current,*map(np.array,item[1:4])
            count=max(24,int(sum(np.linalg.norm(b-a) for a,b in [(p0,p1),(p1,p2),(p2,p3)]))+1)
            for u in np.linspace(0,1,count):
                points.append((1-u)**3*p0+3*(1-u)**2*u*p1+3*(1-u)*u*u*p2+u**3*p3)
            current=p3
        elif cmd=='h' and current is not None and start is not None:
            points.extend(current+(start-current)*u for u in np.linspace(0,1,max(12,int(np.linalg.norm(start-current))+1)))
            current=start
    return points

def check(stem):
    target=ROOT/'figs'/f'{stem}.pdf'
    with pdfplumber.open(target) as doc:
        page=doc.pages[0]; path_points=[]
        for obj in page.curves+page.lines+page.rects:
            if not obj.get('stroke') or not (obj.get('linewidth') or 0)>0: continue
            if obj.get('path'): path_points.extend(sampled_path(obj['path']))
            elif obj.get('pts'):
                pts=obj['pts']
                for a,b in zip(pts[:-1],pts[1:]):
                    path_points.extend(sampled_path([('m',a),('l',b)]))
        samples=np.array(path_points); hits=[]
        for w in page.extract_words(x_tolerance=1,y_tolerance=2):
            x0,y0,x1,y1=w['x0']+1,w['top']+1.5,w['x1']-1,w['bottom']-1.5
            if len(samples) and ((samples[:,0]>x0)&(samples[:,0]<x1)&(samples[:,1]>y0)&(samples[:,1]<y1)).any():
                hits.append({'text':w['text'],'box':[w['x0'],w['top'],w['x1'],w['bottom']]})
        report={'width_pt':page.width,'height_pt':page.height,
                'width_in':page.width/72,'editable_characters':len(page.chars),
                'fonts':sorted({c['fontname'] for c in page.chars}),
                'vector_paths':len(page.curves)+len(page.lines)+len(page.rects),
                'sampled_stroke_points':len(samples),'text_stroke_candidates':hits}
    assert abs(report['width_in']-7.07)<1e-9
    assert report['editable_characters']>100
    pdf=PdfReader(str(target))
    report['font_subtypes']=[str(v.get_object().get('/Subtype')) for v in pdf.pages[0]['/Resources']['/Font'].values()]
    assert '/Type3' not in report['font_subtypes']
    png=Image.open(ROOT/'figs'/f'{stem}.png')
    report['png_pixels']=list(png.size); report['png_dpi']=list(png.info.get('dpi',[]))
    assert png.width==4242
    with pdfium.PdfDocument(str(target)) as doc:
        doc[0].render(scale=180/72).to_pil().save(QA/f'{stem}_pdf_render.png')
    layout=json.loads((QA/f'{stem}_layout.json').read_text())
    report['text_box_candidates']=layout.get('text_intersection_candidates',layout.get('text_intersections',[]))
    report['clipped_text']=layout['clipped_text']
    return report

def main():
    report={stem:check(stem) for stem in STEMS}
    (QA/'export_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    for stem,item in report.items():
        print(stem, 'PDF width',item['width_in'],'PNG',item['png_pixels'],
              'text-stroke candidates',[x['text'] for x in item['text_stroke_candidates']],
              'text-box candidates',len(item['text_box_candidates']),'clipped',len(item['clipped_text']))

if __name__=='__main__': main()
