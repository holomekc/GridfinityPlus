"""Scene statistics for 'Fusion is slow when orbiting / navigating'.

Run inside Fusion (Text Commands window, Py mode):
    exec(open(r'<path to this file>').read())

Navigation cost is drawing cost: number of visible faces / edges, custom
graphics left in the scene, many tiny faces (fillets, magnet holes). The
add-in runs no code while orbiting, so look here, not at the add-in log.
Prints to the Text Commands window and writes scene_stats.txt next to the
add-in log (gridfinityplus.log).
"""
import adsk.core, adsk.fusion, os, time, collections

app = adsk.core.Application.get()
des = adsk.fusion.Design.cast(app.activeProduct)
out = []
say = out.append
t0 = time.perf_counter()

say(f'document: {app.activeDocument.name}  intent: {getattr(des, "designIntent", "?")}')
say(f'timeline: {des.timeline.count} items, {des.timeline.timelineGroups.count} groups')

# Custom graphics left behind (previews that were never cleared).
gfx = 0
for comp in des.allComponents:
    try:
        n = comp.customGraphicsGroups.count
    except Exception:
        n = 0
    if n:
        say(f'  custom graphics groups in "{comp.name}": {n}')
    gfx += n
say(f'custom graphics groups total: {gfx}')

# Bodies / faces / edges (visible ones are what costs while orbiting).
rows = []
totals = collections.Counter()
for comp in des.allComponents:
    occs = des.rootComponent.allOccurrencesByComponent(comp)
    instances = max(1, occs.count) if comp != des.rootComponent else 1
    for b in comp.bRepBodies:
        f, e = b.faces.count, b.edges.count
        vis = b.isLightBulbOn and b.isVisible
        key = 'visible' if vis else 'hidden'
        totals[key + ' bodies'] += instances
        totals[key + ' faces'] += f * instances
        totals[key + ' edges'] += e * instances
        rows.append((f * instances, e * instances, vis, comp.name, b.name))
for k in sorted(totals):
    say(f'{k}: {totals[k]}')
rows.sort(reverse=True)
say('top bodies by faces (faces, edges, visible, component, body):')
for r in rows[:20]:
    say(f'  {r[0]:6d} {r[1]:6d} {"Y" if r[2] else "-"}  {r[3]} / {r[4]}')

# Our features per kind.
kinds = collections.Counter()
for comp in des.allComponents:
    for cf in comp.features.customFeatures:
        try:
            kinds[cf.definition.id] += 1
        except Exception:
            kinds['?'] += 1
say('custom features: ' + ', '.join(f'{k}={v}' for k, v in kinds.items()))

# Bodies whose names look like leftovers of a scratch build.
left = [r for r in rows if any(s in r[4].lower() for s in ('scratch', 'base top section', 'bin body', 'lip body'))]
if left:
    say(f'possible scratch leftovers: {len(left)} (e.g. {left[0][3]} / {left[0][4]})')

say(f'(measured in {(time.perf_counter() - t0) * 1000:.0f} ms)')
text = '\n'.join(out)
print(text)
# Write next to the add-in's log (found through the loaded add-in module).
import sys
target = os.path.join(os.path.expanduser('~'), 'scene_stats.txt')
for name, mod in list(sys.modules.items()):
    if name.endswith('gridfinityUtils.gplog') and hasattr(mod, 'LOG_PATH'):
        target = os.path.join(os.path.dirname(mod.LOG_PATH), 'scene_stats.txt')
        break
with open(target, 'w', encoding='utf-8') as fh:
    fh.write(text)
print('written to', target)
