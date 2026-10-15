"""Shared offline dashboard navigation and native MathML equations.

No external scripts, fonts, renderer, or network connection are required.
"""
from __future__ import annotations

import html
import re


def mi(value):
    return '<mi>'+html.escape(str(value))+'</mi>'


def mn(value):
    return '<mn>'+html.escape(str(value))+'</mn>'


def op(value):
    return '<mo>'+html.escape(str(value))+'</mo>'


def row(*items):
    return '<mrow>'+''.join(items)+'</mrow>'


def sub(base, index):
    return '<msub>'+base+index+'</msub>'


def sup(base, index):
    return '<msup>'+base+index+'</msup>'


def frac(numerator, denominator):
    return '<mfrac>'+numerator+denominator+'</mfrac>'


def hat(value):
    return '<mover accent="true">'+value+'<mo>^</mo></mover>'


def bar(value):
    return '<mover accent="true">'+value+'<mo>¯</mo></mover>'


def absval(value):
    return row(op('|'), value, op('|'))


def parens(value):
    return row(op('('), value, op(')'))


def text(value):
    return '<mtext>'+html.escape(str(value))+'</mtext>'


def math_expression(expression, label, display=True):
    """Wrap already-constructed MathML with an accessible plain-language label."""
    mode = 'block' if display else 'inline'
    result = '<math xmlns="http://www.w3.org/1998/Math/MathML" display="'+mode+'" aria-label="'+html.escape(label, quote=True)+'">'+expression+'</math>'
    return '<div class="math-equation">'+result+'</div>' if display else result


def _equation_bank():
    L,D,C,P,x,q,w,mu,omega,theta,alpha,beta = [mi(v) for v in ('L','D','C','P','x','q','w','μ','ω','θ','α','β')]
    vf,vq,Tf,kj,kc,kq = [sub(mi(a),mi(b)) for a,b in [('v','f'),('v','q'),('T','f'),('k','j'),('k','c'),('k','q')]]
    wi,Ti,vi,qi,Hi = [sub(mi(a),mi('i')) for a in ['w','T','v','q','H']]
    wp,fd,fp = sub(w,text('peak')),sub(mi('f'),mi('d')),sub(mi('f'),mi('p'))
    wh,Ph = hat(bar(w)),hat(P)
    yh,yo = sub(mi('y'),mi('m')),sub(mi('y'),mi('O'))
    ymi,yoi = sub(mi('y'),row(mi('m'),mi('i'))),sub(mi('y'),row(mi('O'),mi('i')))
    sum_i=lambda term:row(sub(op('∑'),mi('i')),term)
    sum_p=lambda term:row(sub(op('∑'),mi('p')),term)
    eq=lambda a,b:row(a,op('='),b)
    rp=lambda speed:row(sub(mi('r'),mi('p')),parens(speed))
    Mp=row(sub(mi('M'),mi('p')),parens(q)); Op=sub(mi('O'),mi('p'))
    tq=sub(bar(mi('t')),mi('q'));tf=sub(bar(mi('t')),mi('f'))
    q0=sub(q,mn(0));mu0=sub(mu,mn(0));omega0=sub(omega,mn(0));kj0=sub(kj,mn(0))
    star=lambda a:sup(a,op('*'))
    bank={
      'wape':(eq(text('WAPE'),row(mn(100),frac(sum_i(absval(row(ymi,op('−'),yoi))),sum_i(absval(yoi))))),'WAPE equals 100 times the sum of absolute method minus reference errors divided by the sum of absolute reference values.'),
      'ape':(eq(text('APE'),row(mn(100),frac(absval(row(yh,op('−'),yo)),absval(yo)))),'Absolute percentage error equals 100 times absolute fitted minus reference, divided by absolute reference.'),
      'delay':(eq(wi,row(Ti,op('−'),frac(L,vf))),'Delay for bin i equals its travel time minus link length divided by free-flow speed.'),
      'average_speed':(eq(bar(mi('v')),frac(row(D,L),sum_i(Hi))),'Average speed equals demand times link length divided by total vehicle-hours.'),
      'demand':(eq(D,sum_i(row(qi,mi('Δt')))),'Episode demand is the sum of per-lane flow times the five-minute interval.'),
      'interval':(eq(mi('Δt'),row(frac(mn(1),mn(12)),text(' h'))),'The sampling interval is one twelfth of an hour.'),
      'demand_capacity':(eq(x,frac(D,C)),'Demand divided by hourly capacity has units of hours.'),
      'free_time':(eq(Tf,frac(L,vf)),'Free-flow travel time is link length divided by free-flow speed.'),
      'duration':(eq(P,row(sub(mi('t'),mn(3)),op('−'),sub(mi('t'),mn(0)))),'Episode duration is end time minus start time.'),
      'observed_peak':(eq(wp,row(frac(L,row(text('min'),parens(vi))),op('−'),Tf)),'Observed peak delay equals length divided by minimum observed speed minus free-flow time.'),
      'observed_mean':(eq(bar(w),frac(sum_i(row(qi,parens(row(frac(L,vi),op('−'),Tf)))),sum_i(qi))),'Observed mean delay is weighted by recorded per-lane flow.'),
      'predicted_duration':(eq(Ph,row(text('max'),parens(row(fd,sup(x,mi('n')),op(','),x)))),'Fitted duration is the maximum of the calibrated power law and demand divided by capacity.'),
      'predicted_peak':(eq(hat(wp),row(Tf,fp,sup(Ph,mi('s')))),'Fitted peak delay equals free-flow time times f p times fitted duration to power s.'),
      'predicted_mean':(eq(wh,row(theta,hat(wp))),'Fitted mean delay equals theta times fitted peak delay.'),
      'predicted_min_speed':(eq(hat(sub(mi('v'),row(mi('t'),mn(2)))),frac(L,row(Tf,op('+'),hat(wp)))),'Fitted minimum whole-link speed equals length divided by free-flow time plus fitted peak delay.'),
      'predicted_average_speed':(eq(hat(bar(mi('v'))),frac(L,row(Tf,op('+'),wh))),'Fitted average speed equals length divided by free-flow time plus fitted mean delay.'),
      'alpha':(eq(alpha,row(theta,fp,sup(fd,mi('s')))),'Alpha equals theta times f p times f d to power s.'),
      'beta':(eq(beta,row(mi('n'),mi('s'))),'Beta equals n times s.'),
      'power_delay':(eq(wh,row(Tf,alpha,sup(x,beta))),'On the power branch, fitted mean delay equals free-flow time times alpha times x to power beta.'),
      'critical_density':(eq(kc,frac(C,vf)),'Triangular critical density equals capacity divided by free-flow speed.'),
      'wave':(eq(omega,frac(C,row(kj,op('−'),kc))),'Backward-wave-speed magnitude equals capacity divided by jam density minus critical density.'),
      'mu_observed':(eq(mu,frac(D,P)),'Observed episode mean flow is demand divided by duration.'),
      'mu_fitted':(eq(hat(mu),frac(D,Ph)),'Fitted episode mean flow is demand divided by fitted duration.'),
      'queue_density':(eq(kq,row(kj,op('−'),frac(mu,omega))),'Congested density equals jam density minus discharge divided by wave-speed magnitude.'),
      'queue_speed':(eq(vq,frac(mu,kq)),'FD-inferred queue speed equals discharge divided by congested density.'),
      'queue_time':(eq(row(tq,parens(q)),frac(row(vf,wh),row(vf,op('−'),q))),'Mean queued-state time equals free-flow speed times fitted mean delay divided by free-flow speed minus candidate queue speed.'),
      'free_state_time':(eq(row(tf,parens(q)),row(Tf,op('−'),frac(row(q,wh),row(vf,op('−'),q)))),'Mean free-state time equals free-flow travel time minus queue speed times fitted mean delay divided by the speed difference.'),
      'two_speed_emission':(eq(Mp,row(D,op('['),tf,parens(q),rp(vf),op('+'),tq,parens(q),rp(q),op(']'))),'Two-speed emission total is demand times free-state time and its rate plus queued-state time and its rate.'),
      'co2_objective':(row(sub(text('minimize'),q),absval(row(frac(row(sub(mi('M'),text('CO₂')),parens(q)),sub(mi('O'),text('CO₂'))),op('−'),mn(1)))),'Minimize the absolute relative CO2 emission error over the physical queue-speed domain.'),
      'balanced_objective':(eq(row(mi('J'),parens(q)),row(frac(mn(1),mn(4)),sum_p(sup(parens(row(frac(Mp,Op),op('−'),mn(1))),mn(2))))),'The balanced objective is one fourth of the sum across pollutants of squared relative emission errors.'),
      'normalized_rmse':(eq(text('Normalized RMSE (%)'),row(mn(100),'<msqrt>'+mi('J')+'</msqrt>')),'Normalized RMSE in percent equals 100 times the square root of the balanced objective.'),
      'physical_queue_bound':(row(mn(0),op('<'),q,op('≤'),frac(L,row(Tf,op('+'),hat(wp)))),'Candidate queue speed must be positive and no greater than length divided by free-flow time plus fitted peak delay.'),
      'recover_mu':(eq(star(mu),frac(row(kj0,q,omega0),row(omega0,op('+'),q))),'Recovered discharge holds jam density and wave speed fixed.'),
      'recover_duration':(eq(star(P),frac(D,star(mu))),'The recovered discharge implies duration D divided by recovered discharge.'),
      'recover_wave':(eq(star(omega),frac(row(mu0,q),row(kj0,q,op('−'),mu0))),'Recovered wave speed holds discharge and jam density fixed; its denominator must be positive.'),
      'recover_density':(eq(star(kj),row(frac(mu0,q),op('+'),frac(mu0,omega0))),'Recovered jam density holds discharge and wave speed fixed.'),
      'capacity_closure':(eq(star(C),frac(row(vf,star(omega),star(kj)),row(vf,op('+'),star(omega)))),'The candidate triangular FD capacity equals free-flow speed times candidate wave speed and jam density, divided by the sum of free-flow and wave speeds.'),
      'exact_fd_curve':(eq(row(kj,parens(omega)),row(frac(mu0,q),op('+'),frac(mu0,omega))),'At fixed discharge and target queue speed, jam density equals discharge over queue speed plus discharge over wave speed.'),
      'capacity_selection':(row(text('minimize'),absval(row(star(C),op('−'),C))),'Among pairs that attain the selected queue speed, minimize the absolute capacity change.'),
    }
    return bank


EQUATIONS = _equation_bank()


def mathml(name, display=True):
    """Return a named, natively typeset equation; unknown names are an error."""
    expression,label = EQUATIONS[name]
    return math_expression(expression,label,display)


CSS = r"""
body.dashboard-shell{max-width:none;margin:0;padding:0;background:#f7f9fc;color:#17324d;font:15px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif}
.dashboard-shell *{box-sizing:border-box}.dashboard-shell a{color:#2563eb}.dashboard-shell [hidden]{display:none!important}
.dashboard-shell .dashboard-main{margin-left:256px;padding:30px 32px 56px;min-width:0;background:white;min-height:100vh;max-width:none}
.dashboard-topbar{display:flex;align-items:center;gap:12px;margin:0 0 24px;padding:0 0 14px;border-bottom:1px solid #d8e1eb;color:#52657a;font-size:13px}
.dashboard-toggle{border:1px solid #a9b9ca;border-radius:6px;background:white;color:#17324d;padding:7px 11px;font:inherit;font-weight:600;cursor:pointer}
.dashboard-shell .dashboard-sidebar{position:fixed;left:0;top:0;bottom:0;width:256px;padding:26px 16px;overflow-y:auto;background:#f0f4f8;border-right:1px solid #cbd6e2;z-index:30;display:block;margin:0}
.dashboard-brand{font-size:18px;font-weight:750;margin:0 10px 4px;line-height:1.3}.dashboard-subtitle{font-size:12px;color:#52657a;margin:0 10px 22px}
.dashboard-shell .dashboard-sidebar nav{display:block;margin:0}.dashboard-sidebar details{margin:8px 0;border:0;padding:0}.dashboard-sidebar summary{font-size:13px;font-weight:700;cursor:pointer;padding:10px 8px;list-style-position:inside;color:#334e68;border-radius:5px}
.dashboard-sidebar details details{margin-left:10px;border-left:1px solid #c9d5e2;padding-left:7px}.dashboard-sidebar a{display:block;padding:9px 10px;margin:3px 0;border-radius:5px;font-size:13px;line-height:1.35;text-decoration:none;color:#334e68;overflow-wrap:anywhere}
.dashboard-sidebar a:hover{background:#e2ebf5}.dashboard-sidebar a[aria-current=page]{background:#dceaff;color:#174caa;font-weight:750;border-left:3px solid #2563eb;padding-left:7px}.dashboard-sidebar .nav-note{font-size:11px;color:#66798e;margin:10px}
.dashboard-shell.dashboard-nav-hidden .dashboard-sidebar{display:none}.dashboard-shell.dashboard-nav-hidden .dashboard-main{margin-left:0}
.dashboard-shell .dashboard-sidebar :focus-visible,.dashboard-toggle:focus-visible{outline:2px solid #2563eb;outline-offset:2px}
.dashboard-shell .dashboard-main h1{font-size:27px;line-height:1.25;margin:0 0 16px}.dashboard-shell .dashboard-main h2{font-size:21px;margin-top:26px}.dashboard-shell .dashboard-main h3{font-size:16px}
.dashboard-shell .math-equation{overflow-x:auto;overflow-y:hidden;padding:8px 2px;margin:7px 0;min-width:0}.dashboard-shell math{font-family:'Cambria Math','STIX Two Math','STIX Math',math;font-size:1.12em}.dashboard-shell math[display=block]{margin:0;text-align:left}.dashboard-shell .equations{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:16px}
.dashboard-shell .equation-card{border:1px solid #d8e0e8;border-radius:7px;padding:16px;min-width:0;background:#fcfdff}.equation-card h3{margin:0 0 12px}.equation-card p{margin:10px 0;color:#415970}
.dashboard-shell .note{background:#f1f5f9;border-left:4px solid #168c69;padding:14px 18px;margin:16px 0}.dashboard-shell .warning{background:#fff7e5;border-left-color:#c58b12}.dashboard-shell .muted{color:#52657a;font-size:13px}
.dashboard-shell .downloads{display:flex;flex-wrap:wrap;gap:10px 20px;margin:18px 0}.dashboard-shell .scroll{overflow:auto;border:1px solid #aebdcd;border-radius:7px;max-width:100%}.dashboard-shell table{border-collapse:separate;border-spacing:0;font-variant-numeric:tabular-nums}.dashboard-shell th,.dashboard-shell td{border-bottom:1px solid #d8e0e8;padding:10px;text-align:right;vertical-align:top}.dashboard-shell th{background:#eaf0f6;font-size:12px}.dashboard-shell td{font-size:13px}.dashboard-shell .group-start{border-left:3px solid #a4b4c5}.dashboard-shell .bad{color:#9a4310;font-weight:650}.dashboard-shell tbody tr:hover td{background:#edf5ff}
.dashboard-shell details:not(.dashboard-sidebar details){margin:18px 0}.dashboard-shell summary{cursor:pointer;font-weight:650}.dashboard-shell code{overflow-wrap:anywhere}
@media(max-width:900px){.dashboard-shell .dashboard-sidebar{position:static;width:auto;border-right:0;border-bottom:1px solid #cbd6e2;padding:16px}.dashboard-shell .dashboard-main{margin-left:0;padding:22px 16px 40px}.dashboard-shell.dashboard-nav-hidden .dashboard-sidebar{display:none}.dashboard-shell .dashboard-sidebar nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px 18px}.dashboard-subtitle{margin-bottom:10px}}
@media print{.dashboard-sidebar,.dashboard-topbar{display:none!important}.dashboard-shell .dashboard-main{margin:0;padding:0}.dashboard-shell .scroll{overflow:visible;max-height:none}.dashboard-shell math{font-size:1em}}
"""


def sidebar(active, prefix='', episode=None):
    esc=html.escape
    def link(key,label,path,local=False):
        return '<a href="'+esc(('' if local else prefix)+path,quote=True)+'"'+(' aria-current="page"' if active==key else '')+'>'+esc(label)+'</a>'
    result='<aside class="dashboard-sidebar" id="dashboard-navigation" aria-label="Dashboard navigation"><p class="dashboard-brand">QVDF-E diagnostics</p><p class="dashboard-subtitle">137 retained average-profile episodes</p><nav>'
    result+='<details open><summary>Experiment results</summary>'+link('index','All episode comparisons','index.html')+link('traffic_parameters','Traffic inputs and calibration','traffic_parameters.html')+'</details>'
    result+='<details open><summary>Emission and FD diagnostics</summary>'+link('inverse_emissions','Emission-target queue speed','inverse_emissions.html')
    result+='<details open><summary>Fundamental diagram</summary>'+link('inverse_fd','Three backward calculations','inverse_fd.html')+link('fd_sensitivity','Bounded parameter pairs','fd_sensitivity.html')+link('fd_summary','Sensitivity summary','fd_summary.html')+link('fd_capacity_comparison','Capacity comparison','fd_capacity_comparison.html')+'</details></details>'
    result+='<details><summary>Separate sensitivity analysis</summary>'+link('capacity_analysis','Capacity sensitivity report','../../../capacity_sensitivity/report.html')+'</details>'
    if episode:
        label=str(episode.get('title') or episode.get('case_id') or 'Current episode')
        result+='<details open><summary>'+esc(label)+'</summary>'+link('episode_traffic','Traffic profiles','index.html',True)
        for pollutant in ['CO2','NOx','CO','HC']:
            result+=link('episode_'+pollutant,{'CO2':'CO₂','NOx':'NOₓ'}.get(pollutant,pollutant)+' emissions','emissions_'+pollutant+'.html',True)
        result+='</details>'
    return result+'</nav><p class="nav-note">Each page contains one main results table. Open a section to reveal its pages. All equations and controls work offline.</p></aside>'


SHELL_SCRIPT = """<script>(()=>{const button=document.getElementById('dashboard-menu-toggle');button.addEventListener('click',()=>{const hidden=document.body.classList.toggle('dashboard-nav-hidden');button.setAttribute('aria-expanded',String(!hidden));button.textContent=hidden?'Show navigation':'Hide navigation'});})();</script>"""


def wrap_document(document, active, prefix='', episode=None):
    """Add the shared shell to an existing full HTML document exactly once."""
    if 'id="dashboard-navigation"' in document:
        raise ValueError('Document already has a dashboard shell.')
    document=re.sub(r'</head\s*>','<style>'+CSS+'</style></head>',document,count=1,flags=re.I)
    match=re.search(r'<body\b([^>]*)>',document,re.I)
    if not match:
        raise ValueError('Expected a complete HTML document with a body element.')
    attrs=match.group(1)
    if re.search(r'\bclass\s*=',attrs,re.I):
        attrs=re.sub(r'(\bclass\s*=\s*[\"\x27])',r'\1dashboard-shell ',attrs,count=1,flags=re.I)
    else:
        attrs+=' class="dashboard-shell"'
    header='<div class="dashboard-topbar"><button id="dashboard-menu-toggle" class="dashboard-toggle" type="button" aria-controls="dashboard-navigation" aria-expanded="true">Hide navigation</button><span>Offline calculation dashboard</span></div>'
    document=document[:match.start()]+'<body'+attrs+'>'+sidebar(active,prefix,episode)+'<main class="dashboard-main" id="dashboard-main">'+header+document[match.end():]
    return re.sub(r'</body\s*>','</main>'+SHELL_SCRIPT+'</body>',document,count=1,flags=re.I)


def render_page(title, body, active, prefix='', episode=None, extra_css='', scripts=''):
    document='<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+extra_css+'</style></head><body>'+body+scripts+'</body></html>\n'
    return wrap_document(document,active,prefix,episode)
