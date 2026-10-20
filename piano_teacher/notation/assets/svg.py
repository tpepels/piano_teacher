"""Shared extraction of an authentic SVG fragment including its source transforms."""
from __future__ import annotations
import copy
from xml.etree import ElementTree as ET

def isolate(root: ET.Element, target: ET.Element) -> str:
    """Keep the original XML graphics and inherited transforms/defs."""
    clone = copy.deepcopy(root)
    # Node identity changes on deepcopy: retain the child-index path.
    path=[]
    def locate(node):
        if node is target:
            return True
        for index,child in enumerate(node):
            path.append(index)
            if locate(child):
                return True
            path.pop()
        return False
    if not locate(root):
        raise ValueError("Detached Verovio source node")
    selected=clone
    for index in path:
        selected=selected[index]

    def trim(node):
        if node is selected:
            for el in node.iter():
                for child in list(el):
                    if set(child.get("class","").split()) & {"bounding-box","content-bounding-box"}:
                        el.remove(child)
            return True
        if node.tag.rsplit("}",1)[-1] in {"defs","style"}:
            return True
        yes=False
        for child in list(node):
            if trim(child):
                yes=True
            else:
                node.remove(child)
        return yes
    trim(clone)
    return ET.tostring(clone,encoding="unicode")


