"""
GridfinityPlus file logger.

Writes to <addin>/gridfinityplus.log so the developer can read exactly what
happened (steps, timings, timeline state) after a repro session in Fusion.
Cheap append-per-line; fine for interactive debugging.
"""

import os
import time
import datetime
import traceback

import adsk.core, adsk.fusion

LOG_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'gridfinityplus.log'))


def log(msg: str):
    stamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f'[{stamp}] {msg}\n')
    except Exception:
        pass


def logExc(prefix: str):
    log(f'{prefix} EXCEPTION:\n{traceback.format_exc()}')


def session(title: str):
    log('=' * 60)
    log(f'SESSION: {title}')
    log(f'  document: {documentInfo()}')


def documentInfo() -> str:
    """Document name, design type and design intent (Part / Assembly /
    Hybrid) - custom feature editing depends on them."""
    try:
        app = adsk.core.Application.get()
        des = adsk.fusion.Design.cast(app.activeProduct)
        if des is None:
            return 'no design'
        intent = '?'
        try:
            types = adsk.fusion.DesignIntentTypes
            names = {getattr(types, n): n.replace('DesignIntentType', '')
                     for n in dir(types) if n.endswith('DesignIntentType')}
            intent = names.get(des.designIntent, str(des.designIntent))
        except Exception:
            intent = 'n/a'
        dtype = 'Parametric' if des.designType == adsk.fusion.DesignTypes.ParametricDesignType else 'Direct'
        return f'"{app.activeDocument.name}" type={dtype} intent={intent}'
    except Exception as err:
        return f'unknown ({err})'


class timed:
    """Context manager: with timed('build'): ... -> logs duration in ms."""

    def __init__(self, label: str):
        self.label = label

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        dt = (time.perf_counter() - self.t0) * 1000
        log(f'TIMING {self.label}: {dt:.0f} ms')
        return False


def dumpTimeline(des: adsk.fusion.Design, tag: str):
    """Log every timeline node: index, type, name, health."""
    try:
        tl = des.timeline
        log(f'TIMELINE [{tag}] count={tl.count} marker={tl.markerPosition}')
        for i in range(tl.count):
            item = tl.item(i)
            try:
                entity = item.entity
                etype = entity.objectType.split('::')[-1] if entity else '<no entity>'
            except Exception:
                etype = '<entity error>'
            name = '?'
            try:
                name = item.name
            except Exception:
                pass
            health = ''
            try:
                if item.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
                    health = f' HEALTH={item.healthState}'
            except Exception:
                pass
            group = ' [GROUP]' if item.isGroup else ''
            log(f'  #{i}: {etype} "{name}"{group}{health}')
    except Exception:
        logExc(f'dumpTimeline[{tag}]')


def dumpBodies(component: adsk.fusion.Component, tag: str):
    try:
        names = []
        for i in range(component.bRepBodies.count):
            b = component.bRepBodies.item(i)
            names.append(f'{b.name}(faces={b.faces.count},visible={b.isLightBulbOn})')
        log(f'BODIES [{tag}] {component.name}: {names}')
    except Exception:
        logExc(f'dumpBodies[{tag}]')
