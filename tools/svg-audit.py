import re, sys, unicodedata
from lxml import etree

# Windows 控制台默认 GBK，输出含 ◐/→ 等符号时会 UnicodeEncodeError，强制 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SRC = 'wlv-uip-syrs-arch-2026.html'
html = open(SRC, encoding='utf-8').read()
# svg chunks
svgs = re.findall(r'<svg\b.*?</svg>', html, re.S)

def width_est(s, fs, mono=True):
    w = 0.0
    for ch in s:
        if ch == ' ':
            w += fs * (0.6 if not mono else 0.6)
        elif ord(ch) < 0x2000:
            w += fs * (0.60 if mono else 0.55)
        elif ch in '·↔→←≥≤±×—～~≈':
            w += fs * (0.6 if not mono else 0.62)
        else:
            w += fs
    return w

def cls_fs(cl, tmhl=False):
    if 'tt' in cl: return 13.0
    if 'ts' in cl: return 11.0
    if 'tm' in cl: return 11.5 if 'tm-hl' in cl else 10.5
    return 12.0

for i, svg in enumerate(svgs):
    root = etree.fromstring(svg.encode())
    vb = root.get('viewBox')
    if not vb:
        print(f'--- SVG {i}: no viewBox'); continue
    _, _, W, H = [float(v) for v in vb.split()]
    items = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.split('}')[-1]
        if tag == 'rect':
            try:
                x = float(el.get('x', 0)); y = float(el.get('y', 0))
                w = float(el.get('width', 0)); h = float(el.get('height', 0))
                items.append(('rect', x, y, w, h, '', ' '.join(el.get('class', '').split())))
            except ValueError:
                pass
        elif tag == 'text':
            x = float(el.get('x', 0)); y = float(el.get('y', 0))
            anchor = el.get('text-anchor', 'start')
            cl = ' '.join(el.get('class', '').split())
            txt = ''.join(el.itertext()).strip()
            ov = re.search(r'font-size:\s*([\d.]+)px', el.get('style', '') or '')
            fs = float(ov.group(1)) if ov else cls_fs(cl)
            w = width_est(txt, fs) * 1.055
            if anchor == 'middle': x0 = x - w / 2
            elif anchor == 'end': x0 = x - w
            else: x0 = x
            items.append(('text', x0, y, w, fs, txt, cl))
    probs = []
    # a) viewBox overflow
    for it in items:
        if it[0] != 'text': continue
        _, x0, y, w, fs, txt, cl = it
        if x0 < -0.5 or x0 + w > W + 0.5:
            probs.append(f'OUT[{x0:.0f},{x0+w:.0f} of {W:.0f}] {txt[:40]!r}')
    # b) text covered by later rect
    for idx, it in enumerate(items):
        if it[0] != 'text': continue
        _, x0, y, w, fs, txt, cl = it
        cx, cy = x0 + w / 2, y - fs * 0.33
        for jt in items[idx+1:]:
            if jt[0] != 'rect': continue
            _, rx, ry, rw, rh, _, rcl = jt
            if rw <= 0 or rh <= 0: continue
            if rx + 0.6 <= cx <= rx + rw - 0.6 and ry + 0.6 <= cy <= ry + rh - 0.6:
                # ignore tiny decorative rects (lines drawn as rects)
                if rw > 20 and rh > 12:
                    probs.append(f'COVERED({rcl}) {txt[:40]!r}')
                break
    # c) text-text collision
    tx = [it for it in items if it[0] == 'text']
    for a in range(len(tx)):
        for b in range(a + 1, len(tx)):
            A, B = tx[a], tx[b]
            ax0, ay, aw, afs = A[1], A[2], A[3], A[4]
            bx0, by, bw, bfs = B[1], B[2], B[3], B[4]
            ay0, ay1 = ay - afs * 0.92, ay + afs * 0.28
            by0, by1 = by - bfs * 0.92, by + bfs * 0.28
            ox = min(ax0 + aw, bx0 + bw) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > 1.5 and oy > 1.5:
                probs.append(f'TXT-OVERLAP {A[5][:26]!r} | {B[5][:26]!r} ox={ox:.0f} oy={oy:.0f}')
    # d) text spilling out of its containing rect
    for it in tx:
        _, x0, y, w, fs, txt, cl = it
        best = None
        for jt in items:
            if jt[0] != 'rect': continue
            _, rx, ry, rw, rh, _, rcl = jt
            if rw < 20 or rh < 12: continue
            if rx <= x0 + 1 <= rx + rw and ry <= y - 1 <= ry + rh:
                if best is None or rw * rh < best[3] * best[4]:
                    best = jt
        if best:
            _, rx, ry, rw, rh, _, rcl = best
            if x0 + w > rx + rw + 1.5:
                probs.append(f'SPILL({rcl}) box[{rx:.0f},{rx+rw:.0f}] text[{x0:.0f},{x0+w:.0f}] {txt[:34]!r}')
    seen = set(); uniq = []
    for p in probs:
        if p not in seen: seen.add(p); uniq.append(p)
    print(f'--- SVG {i} viewBox 0 0 {W:.0f} {H:.0f}  problems={len(uniq)}')
    for p in uniq[:40]:
        print('   ', p)
