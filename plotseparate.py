#!/usr/bin/env python3
"""Ultra-lightweight spectroscopy scan plotter."""
import sys, os, argparse
import numpy as np
import matplotlib.pyplot as plt

def load(p):
    with open(p) as f: lines = f.read().splitlines()
    meta, wl, rows = {}, None, []
    for l in lines:
        l = l.strip()
        if not l: continue
        if l[0] == '#':
            if 'wavelength_nm:' in l:
                parts = l.split(':', 1)
                if len(parts) > 1:
                    wl = np.array([float(x) for x in parts[1].split()])
            else:
                content = l[1:].strip()
                if ':' in content:  # ✅ FIX: Safety check for missing colons
                    k, v = content.split(':', 1)
                    meta[k.strip()] = v.strip()
            continue
        if wl is None: continue
        rows.append(list(map(float, l.split('\t'))))
    if not rows or wl is None: raise ValueError("Invalid file format")
    d = np.array(rows); n = (d.shape[1] - 4) // 2
    return dict(
        meta=meta, wl=wl[:n], ang=d[:,0], v=d[:,1], i=d[:,2],
        comp=d[:,3].astype(bool), raw=d[:,4:4+n], corr=d[:,4+n:4+2*n]
    )

def plot(d, raw=False):
    sp = d['raw'] if raw else d['corr']
    wl, ag = d['wl'], d['ang']; n = len(ag)
    cmap = plt.cm.plasma(np.linspace(0, 1, n))
    lbl = 'Raw' if raw else 'Corrected'

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
    
    # 1. Waterfall
    for i in range(n): ax1.plot(wl, sp[i], c=cmap[i], lw=0.8, alpha=0.7)
    ax1.set_ylabel(lbl); ax1.grid(True, alpha=0.2)
    fig.colorbar(plt.cm.ScalarMappable(cmap='plasma', norm=plt.Normalize(ag.min(), ag.max())).set_array([]), 
                 ax=ax1, label='Angle (°)')

    # 2. Heatmap
    ax2.imshow(sp, aspect='auto', cmap='inferno', origin='upper', 
               extent=[wl[0], wl[-1], ag[-1], ag[0]])
    ax2.set_ylabel('Angle (°)'); ax2.grid(True, alpha=0.2)
    fig.colorbar(ax2.images[0], ax=ax2, label=lbl)

    # 3. Integrated + Electrical
    integrated = sp.sum(1)
    ax3.plot(ag, integrated, 'o-', c='#2980b9', lw=1.5)
    if d['comp'].any():
        ax3.scatter(ag[d['comp']], integrated[d['comp']], c='r', marker='x', s=50, zorder=5)
    ax3.axhline(0, c='k', lw=0.5); ax3.set_ylabel('Integrated counts'); ax3.grid(True, alpha=0.2)
    
    ax3t = ax3.twinx()
    ax3t.plot(ag, d['v'], 's-', c='#27ae60', lw=1.2)
    ax3t.plot(ag, d['i'] * 1e3, 's-', c='#c09066', lw=1.2)
    ax3t.set_ylabel('V / mA')
    for a, c in zip(ag, d['comp']):
        if c: ax3.axvline(a, c='r', ls='--', alpha=0.4)

    fig.suptitle(os.path.basename(d['path']), fontsize=11)
    fig.tight_layout(); plt.show()

if __name__ == '__main__':
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument('file', nargs='?')
    p.add_argument('--raw', action='store_true')
    args = p.parse_args()
    
    path = args.file or input('File path: ').strip()
    if not os.path.isfile(path): sys.exit(f'Not found: {path}')
    
    d = load(path)
    pk = d['corr'].argmax(); r, c = np.unravel_index(pk, d['corr'].shape)
    print(f"\n  {os.path.basename(d['path'])}\n"
          f"  Angles: {len(d['ang'])} ({d['ang'][0]:.1f}→{d['ang'][-1]:.1f}°)\n"
          f"  Wavelengths: {len(d['wl'])} ({d['wl'][0]:.1f}–{d['wl'][-1]:.1f} nm)\n"
          f"  Compliance: {d['comp'].sum()}/{len(d['comp'])}\n"
          f"  Peak: {d['corr'][r,c]:.1f} @ {d['wl'][c]:.2f} nm")
    for k, v in d['meta'].items(): print(f"  {k:<16}: {v}")
    
    plot(d, args.raw)
