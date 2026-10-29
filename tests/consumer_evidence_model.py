"""Independent closed A2 content family. No Fruth runtime imports."""
from html.parser import HTMLParser
from html import escape
import json
import re

from hypothesis import strategies as st
from tests.persistence_trace_adapter import collect_traces

SEED = 2026102403
FAULTS = ('none', 'omit_subject', 'wrong_subject', 'omit_version', 'wrong_version',
          'omit_values', 'wrong_values', 'omit_sum', 'wrong_sum', 'omit_css', 'separate_css')
REVIEWS = ('native', 'missing', 'negative', 'passed', 'wrong_binding', 'missing_criterion', 'wrong_refs')
BINDINGS = ('none', 'read_identity', 'source_digest', 'output_digest')
CRITERIA = ('rendered subject and version match the saved source',
            'rendered values and arithmetic sum match the saved source',
            'requested CSS is embedded without a separate output')


def case(subject='alpha', version=1, values=(7, 11), css=True, variant=0,
         fault='none', review='native', binding='none'):
    return dict(subject=subject, version=version, values=list(values), css=css,
                variant=variant, fault=fault, review=review, binding=binding)


def requirements(c):
    data={k:c[k] for k in ('subject','version','values')}
    prompt=('Save numbers.json containing '+json.dumps(data,sort_keys=True,separators=(',',':'))+
            '. Read the actually saved file again. Create result.html from the read data '
            'with the subject, version, values and sum'+(' and embedded CSS.' if c['css'] else '.'))
    return dict(data=data, prompt=prompt, css=c['css'], outputs=['numbers.json','result.html'])


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text=[]; self.hidden=0; self.style=0; self.css=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','head'): self.hidden+=1
        if tag=='style': self.style+=1
        if any(k=='style' and v and ':' in v for k,v in attrs): self.css=True
        self.text.append(' ')
    def handle_endtag(self,tag):
        if tag=='style': self.style=max(0,self.style-1)
        if tag in ('script','style','head'): self.hidden=max(0,self.hidden-1)
        self.text.append(' ')
    def handle_data(self,data):
        if self.style and re.search(r'[^{}]+\{[^{}]*:[^{}]+\}',data): self.css=True
        if not self.hidden: self.text.append(data)


def oracle(req, html, outputs):
    """Labels give unambiguous meaning; tags/order/whitespace aren't prescribed.

    Closed family uses Subject/Version/Values/Sum labels, optionally : or =.
    Values can use commas, spaces, slash or 'and'. Equivalent layouts can nest
    tags, use tables/paragraphs/dl, and CSS can use style blocks or attributes.
    This is not a general browser, natural-language or CSS correctness verifier.
    """
    p=VisibleHTML(); p.feed(html); p.close()
    text=' '.join(''.join(p.text).split())
    pairs=re.findall(r'\b(subject|version|values|sum)\b\s*[:=]?\s*(.*?)(?=\b(?:subject|version|values|sum)\b|$)',text,re.I)
    fields={}
    for label,value in pairs: fields.setdefault(label.lower(),[]).append(value.strip(' ;.'))
    data=req['data']
    def single(key): return fields.get(key,[]) if len(fields.get(key,[]))==1 else []
    def ints(key):
        items=single(key)
        return [int(n) for n in re.findall(r'-?\d+',items[0])] if items else []
    checks={'subject':single('subject')==[data['subject']],
            'version':ints('version')==[data['version']],
            # Caller asks to present both values, not to preserve display order.
            # Multiplicity still matters when the two source integers are equal.
            'values':sorted(ints('values'))==sorted(data['values']),
            'sum':ints('sum')==[data['values'][0]+data['values'][1]],
            'embedded_css':not req['css'] or p.css,
            'output_scope':sorted(outputs)==sorted(req['outputs'])}
    return dict(checks=checks, correct=all(checks.values()), visible_text=text)


def provider_html(data,c):
    """Controlled producer response; consumes only data parsed from actual packet."""
    rendered={'Subject':str(data['subject']),'Version':str(data['version']),
              'Values':', '.join(str(n) for n in data['values']),
              'Sum':str(sum(data['values']))}
    fault=c['fault']
    if fault.startswith('omit_') and fault[5:].title() in rendered: rendered.pop(fault[5:].title())
    if fault=='wrong_subject': rendered['Subject']='beta' if data['subject']=='alpha' else 'alpha'
    if fault=='wrong_version': rendered['Version']=str(data['version']+1)
    if fault=='wrong_values': rendered['Values']=f"{data['values'][0]+1}, {data['values'][1]}"
    if fault=='wrong_sum': rendered['Sum']=str(sum(data['values'])+1)
    pairs=list(rendered.items()); css=c['css'] and fault not in ('omit_css','separate_css')
    if c['variant']==0:
        body=''.join(f'<p>{k}: {escape(v)}</p>' for k,v in pairs)
    elif c['variant']==1:
        body='<table>'+''.join(f'<tr><th>{k}</th><td>{escape(v)}</td></tr>' for k,v in reversed(pairs))+'</table>'
    else:
        body='<dl>'+''.join(f'<dt><strong>{k}</strong></dt><dd>{escape(v.replace(", "," and "))}</dd>' for k,v in pairs[1:]+pairs[:1])+'</dl>'
    style='<style>body { color: navy; }</style>' if css and c['variant']!=2 else ''
    attr=' style="color:navy"' if css and c['variant']==2 else ''
    return f'<!doctype html><html><head><title>Result</title>{style}</head><body{attr}>{body}</body></html>'


def controls():
    result=[('positive',case()),('equivalent-table',case(variant=1)),
            ('equivalent-inline-css',case(variant=2)),('css-not-requested',case(css=False))]
    result += [(f,case(fault=f)) for f in FAULTS[1:]]
    result += [('binding-'+b,case(binding=b)) for b in BINDINGS[1:]]
    result += [('review-'+r,case(review=r)) for r in REVIEWS[1:]]
    result += [('false-positive-review',case(fault='wrong_sum',review='passed')),
               ('negative-wrong-content',case(fault='wrong_subject',review='negative'))]
    return result


def corpus():
    strategy=st.fixed_dictionaries({
        'subject':st.sampled_from(('alpha','beta')), 'version':st.integers(1,3),
        'values':st.lists(st.integers(-20,40),min_size=2,max_size=2),
        'css':st.booleans(),'variant':st.integers(0,2),
        'fault':st.sampled_from(FAULTS),'review':st.sampled_from(REVIEWS),
        'binding':st.sampled_from(BINDINGS)})
    generated=collect_traces(seed_value=SEED,examples=24,strategy=strategy,validator=lambda c: requirements(c))
    seeds=[case(),case(fault='wrong_sum'),case(fault='omit_css'),case(review='missing'),
           case(review='passed',fault='wrong_sum'),case(review='negative'),
           case(review='wrong_binding'),case(binding='output_digest')]
    return {'seed':SEED,'generated_examples':24,'scenario_limit':32,'transition_limit':32,
            'entries':[{'label':f'seed-{i:02}','origin':'seeded','case':c} for i,c in enumerate(seeds)]+
                      [{'label':f'generated-{i:02}','origin':'generated','case':c} for i,c in enumerate(generated)]}
