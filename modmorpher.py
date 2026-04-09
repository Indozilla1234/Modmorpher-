from __future__ import annotations

Tool_Version = "1.5"

import os
import json
import uuid
import zipfile
import shutil
import builtins
import time
import sys
import math
import subprocess
import re
from typing import Optional, Tuple, Dict, Set, List, Union
try:
    from tqdm import tqdm as _tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    _tqdm = None
class _ProgressLogger:
    _scary = (
        "", "warn", "Warn", "WARN", "[WARN]",
        "missing", "Missing", "placeholder", "fallback",
        "skipped", "Skipped",
    )
    _bad_words = (
        "", "error", "Error", "ERROR",
        "failed", "Failed", "exception", "Exception",
        "crash", "Crash",
    )
    def __init__(self):
        self._original_print = builtins.print
        self._active_bar = None
        self._intercepting = False
        self._deferred_messages: list = []
    def write(self, *args, **kwargs):
        text = " ".join(str(a) for a in args)
        if self._intercepting and self._active_bar is not None:
            if self._is_visible(text):
                _tqdm.write(self._format(text))
        else:
            self._original_print(text, **{k: v for k, v in kwargs.items() if k != "end"})
    def warn(self, text: str):
        msg = f"    {text}"
        if self._intercepting and self._active_bar is not None:
            _tqdm.write(msg)
        else:
            self._original_print(msg)
    def error(self, text: str):
        msg = f"    {text}"
        if self._intercepting and self._active_bar is not None:
            _tqdm.write(msg)
        else:
            self._original_print(msg)
    class _Phase:
        def __init__(self, logger, desc, total, unit, colour):
            self._logger = logger
            self._desc = desc
            self._total = total
            self._unit = unit
            self._colour = colour
            self._bar = None
        def __enter__(self):
            if TQDM_AVAILABLE:
                bar_fmt = (
                    "  {desc:<38} {bar} {percentage:3.0f}%  "
                    "{n_fmt}/{total_fmt} {unit} [{elapsed}]{postfix}"
                )
                self._bar = _tqdm(
                    total=self._total if self._total > 0 else None,
                    desc=self._desc,
                    unit=self._unit,
                    colour=self._colour,
                    bar_format=bar_fmt if self._total > 0 else None,
                    dynamic_ncols=True,
                    leave=True,
                )
                self._logger._active_bar = self._bar
                self._logger._intercepting = True
                builtins.print = self._logger.write
            else:
                builtins.print(f"\n── {self._desc} ──")
            return self
        def __exit__(self, *_):
            builtins.print = self._logger._original_print
            self._logger._intercepting = False
            self._logger._active_bar = None
            if self._bar is not None:
                self._bar.close()
        def update(self, n: int = 1):
            if self._bar:
                self._bar.update(n)
        def set_postfix_str(self, s: str):
            if self._bar:
                self._bar.set_postfix_str(s, refresh=False)
        def set_description(self, s: str):
            if self._bar:
                self._bar.set_description(s, refresh=True)
    def phase(self, desc: str, total: int = 0,
              unit: str = "file", colour: str = "cyan"):
        return self._Phase(self, desc, total, unit, colour)
    def _is_visible(self, text: str) -> bool:
        for p in self._ERROR_PATTERNS:
            if p in text:
                return True
        for p in self._WARN_PATTERNS:
            if p in text:
                return True
        return False
    @staticmethod
    def _format(text: str) -> str:
        return f"    {text}"
_logger = _ProgressLogger()
_ALL_JAVA_FILES: Dict[str, str] = {}
_RP_ASSET_INDEX: Dict[str, Union[list, dict]] = {"textures": [], "geometry": [], "flipbook_textures": {}}
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
    PIL_AVAILABLE = True
JAVALANG_AVAILABLE = False
try:
    import javalang
    JAVALANG_AVAILABLE = True
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "javalang"])
        import javalang
        JAVALANG_AVAILABLE = True
    except Exception:
        JAVALANG_AVAILABLE = False
class JavaAST:
    def __init__(self, source: str):
        self._src = source
        self._tree: Optional[object] = None
        self._parsed = False
    def _parse(self):
        if self._parsed:
            return
        self._parsed = True
        if not JAVALANG_AVAILABLE:
            return
        try:
            self._tree = javalang.parse.parse(self._src)
        except Exception:
            self._tree = None
    def get_class_declarations(self) -> List:
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            results.append(node)
        return results
    def primary_class_name(self) -> Optional[str]:
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            return node.name
        for _, node in self._tree.filter(javalang.tree.InterfaceDeclaration):
            return node.name
        for _, node in self._tree.filter(javalang.tree.EnumDeclaration):
            return node.name
        return None
    def superclass_name(self, cls_name: Optional[str] = None) -> Optional[str]:
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if cls_name and node.name != cls_name:
                continue
            if node.extends and hasattr(node.extends, 'name'):
                return node.extends.name
        return None
    def implemented_interfaces(self, cls_name: Optional[str] = None) -> List[str]:
        self._parse()
        if not self._tree:
            return []
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if cls_name and node.name != cls_name:
                continue
            if node.implements:
                return [i.name for i in node.implements if hasattr(i, 'name')]
        return []
    def class_extends(self, target_name: str, cls_name: Optional[str] = None) -> bool:
        self._parse()
        if not self._tree:
            return False
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if cls_name and node.name != cls_name:
                continue
            if node.extends and hasattr(node.extends, 'name'):
                if node.extends.name == target_name:
                    return True
        return False
    def all_class_extends(self) -> List[Tuple[str, str]]:
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if node.extends and hasattr(node.extends, 'name'):
                results.append((node.name, node.extends.name))
        return results
    def annotation_value(self, annotation_name: str) -> Optional[str]:
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if not node.annotations:
                continue
            for ann in node.annotations:
                if ann.name == annotation_name:
                    if ann.element and hasattr(ann.element, 'value'):
                        v = ann.element.value
                        return v.strip('"').strip("'") if isinstance(v, str) else str(v)
        return None
    def field_string_values(self, field_names: Set[str]) -> Dict[str, str]:
        self._parse()
        if not self._tree:
            return {}
        results = {}
        for _, node in self._tree.filter(javalang.tree.FieldDeclaration):
            for decl in node.declarators:
                if decl.name in field_names and decl.initializer:
                    init = decl.initializer
                    if isinstance(init, javalang.tree.Literal) and init.value:
                        val = init.value.strip('"').strip("'")
                        results[decl.name] = val
        return results
    def all_string_literals(self) -> List[str]:
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.Literal):
            if node.value and node.value.startswith('"'):
                results.append(node.value.strip('"'))
        return results
    def method_names(self) -> Set[str]:
        self._parse()
        if not self._tree:
            return set()
        names = set()
        for _, node in self._tree.filter(javalang.tree.MethodDeclaration):
            names.add(node.name)
        return names
    def invocations_of(self, method_name: str) -> List:
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.MethodInvocation):
            if node.member == method_name:
                results.append(node)
        return results
    def object_creations_of(self, class_name: str) -> List:
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassCreator):
            if hasattr(node.type, 'name') and node.type.name == class_name:
                results.append(node)
        return results
    def all_object_creation_types(self) -> List[str]:
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassCreator):
            if hasattr(node.type, 'name'):
                results.append(node.type.name)
        return results
    def method_body_source(self, method_name: str) -> Optional[str]:
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.MethodDeclaration):
            if node.name != method_name:
                continue
            if node.position:
                lines = self._src.splitlines()
                start_line = node.position.line - 1
                snippet = "\n".join(lines[start_line:start_line + 200])
                brace_open = snippet.find('{')
                if brace_open == -1:
                    return snippet
                depth, i = 0, brace_open
                while i < len(snippet):
                    if snippet[i] == '{':
                        depth += 1
                    elif snippet[i] == '}':
                        depth -= 1
                        if depth == 0:
                            return snippet[brace_open:i + 1]
                    i += 1
                return snippet[brace_open:]
        return None
    def instanceof_types(self) -> Set[str]:
        self._parse()
        if not self._tree:
            return set()
        types = set()
        for _, node in self._tree.filter(javalang.tree.BinaryOperation):
            if node.operator == 'instanceof' and hasattr(node.operandr, 'name'):
                types.add(node.operandr.name)
        for _, node in self._tree.filter(javalang.tree.MethodInvocation):
            pass
        return types
    @staticmethod
    def strip_generics(name: str) -> str:
        idx = name.find('<')
        return name[:idx].strip() if idx != -1 else name.strip()
    @staticmethod
    def first_string_arg(invocation_node) -> Optional[str]:
        args = getattr(invocation_node, 'arguments', None) or []
        for arg in args:
            if isinstance(arg, javalang.tree.Literal) and arg.value and arg.value.startswith('"'):
                return arg.value.strip('"')
        return None
    @staticmethod
    def translate_java_body_to_js(java_body: str, event_type: str, param: str, namespace: str, safe_name: str) -> list:
        if not JAVALANG_AVAILABLE:
            return []

        dummy_code = f"""
public class Dummy {{
    public void dummy() {{
        {java_body}
    }}
}}
"""
        try:
            tree = javalang.parse.parse(dummy_code)
            lines = []
            player = _get_player_var(event_type, param)

            for path, node in tree:
                if isinstance(node, javalang.tree.MethodDeclaration) and node.name == 'dummy':
                    for stmt in node.body:
                        js_stmts = translate_statement(stmt, player, namespace)
                        lines.extend(js_stmts)
            return lines
        except Exception:
            return []

def translate_method_invocation(invocation: object, player: str, namespace: str, symbol_table: JavaSymbolTable) -> Optional[str]:

    member = getattr(invocation, 'member', '')
    qualifier = getattr(invocation, 'qualifier', None)
    if qualifier and isinstance(qualifier, str):
        pass                         
    elif qualifier and isinstance(qualifier, list) and len(qualifier) == 1:
        qualifier = qualifier[0]
    else:
        qualifier = None
    args = getattr(invocation, 'arguments', [])

    if member == 'receiveEnergy':
        if args and isinstance(args[0], javalang.tree.Literal):
            amt = args[0].value
            return f'    receiveEnergy({player}, {amt});'
    elif member == 'extractEnergy':
        if args and isinstance(args[0], javalang.tree.Literal):
            amt = args[0].value
            return f'    extractEnergy({player}, {amt});'


    nbt_result = NBTTranslator.translate_nbt_call(member, args, namespace, player)
    if nbt_result:
        return nbt_result


    cap_type = symbol_table.method_belongs_to_capability(member)
    if cap_type:
        if cap_type == 'energy' and member not in ('receiveEnergy', 'extractEnergy'):

            if member == 'getEnergyStored':
                return f'getEnergyStored({player})'
        elif cap_type == 'fluid':
            if member == 'fill' and len(args) >= 2:
                fluid_stack = translate_expression(args[0])
                return f'    fill({player}, {fluid_stack});'
            elif member == 'drain' and len(args) >= 1:
                amount = translate_expression(args[0])
                return f'    drain({player}, {amount});'


    bedrock_call = JavaToBedrockMethodMap.translate_method_call(member, args, qualifier)
    if bedrock_call:
        return bedrock_call


    return None

def translate_statement(stmt: object, player: str, namespace: str, symbol_table: JavaSymbolTable) -> list:
    if isinstance(stmt, javalang.tree.StatementExpression):
        expr = stmt.expression
        if isinstance(expr, javalang.tree.MethodInvocation):
            js_line = translate_method_invocation(expr, player, namespace, symbol_table)
            return [js_line] if js_line else []
        elif isinstance(expr, javalang.tree.Assignment):

            left = translate_expression(expr.expressionl)
            right = translate_expression(expr.value)
            if left and right:
                return [f'    {left} = {right};']
    elif isinstance(stmt, javalang.tree.LocalVariableDeclaration):

        type_name = stmt.type.name if hasattr(stmt.type, 'name') else str(stmt.type)
        js_type = 'let'                  
        for decl in stmt.declarators:
            var_name = decl.name
            init = ''
            if decl.initializer:
                init_val = translate_expression(decl.initializer)
                if init_val:
                    init = f' = {init_val}'
            return [f'    {js_type} {var_name}{init};']
    elif isinstance(stmt, javalang.tree.IfStatement):

        condition = translate_expression(stmt.condition)
        if condition:
            lines = [f'    if ({condition}) {{']

            then_stmts = stmt.then_statement
            if isinstance(then_stmts, javalang.tree.BlockStatement):
                for s in then_stmts.statements:
                    lines.extend(translate_statement(s, player, namespace))
            elif isinstance(then_stmts, list):
                for s in then_stmts:
                    lines.extend(translate_statement(s, player, namespace))
            else:
                lines.extend(translate_statement(then_stmts, player, namespace))
            lines.append('    }')
            if stmt.else_statement:
                lines.append('    else {')
                else_stmts = stmt.else_statement
                if isinstance(else_stmts, javalang.tree.BlockStatement):
                    for s in else_stmts.statements:
                        lines.extend(translate_statement(s, player, namespace))
                elif isinstance(else_stmts, list):
                    for s in else_stmts:
                        lines.extend(translate_statement(s, player, namespace))
                else:
                    lines.extend(translate_statement(else_stmts, player, namespace))
                lines.append('    }')
            return lines
    elif isinstance(stmt, javalang.tree.ReturnStatement):

        if stmt.expression:
            expr = translate_expression(stmt.expression)
            return [f'    return {expr};'] if expr else ['    return;']
        else:
            return ['    return;']
    elif isinstance(stmt, javalang.tree.ForStatement):

        init = stmt.initialization
        condition = translate_expression(stmt.condition) if stmt.condition else None
        update = stmt.update
        lines = []
        if condition:
            lines.append(f'    for (let i = 0; {condition}; i++) {{')

            if stmt.body:
                body_list = stmt.body if isinstance(stmt.body, list) else [stmt.body]
                for s in body_list:
                    lines.extend(translate_statement(s, player, namespace))
            lines.append('    }')
        return lines

    return []

def translate_expression(expr: object) -> Optional[str]:
    if isinstance(expr, javalang.tree.Literal):
        return str(expr.value)
    elif isinstance(expr, javalang.tree.MemberReference):
        return expr.member
    elif isinstance(expr, javalang.tree.MethodInvocation):

        member = getattr(expr, 'member', '')
        args = getattr(expr, 'arguments', [])
        arg_strs = []
        for arg in args:
            arg_trans = translate_expression(arg)
            if arg_trans:
                arg_strs.append(arg_trans)
        return f'{member}({", ".join(arg_strs)})'
    elif isinstance(expr, javalang.tree.BinaryOperation):
        left = translate_expression(expr.operandl)
        right = translate_expression(expr.operandr)
        op = expr.operator
        if left and right:
            return f'{left} {op} {right}'

    return None

def detect_tick_method(java_code: str) -> Optional[Tuple[str, str]]:
    if not JAVALANG_AVAILABLE:
        return None
    try:
        tree = javalang.parse.parse(java_code)
        for _, node in tree:
            if isinstance(node, javalang.tree.MethodDeclaration):
                if node.name in ('onTick', 'tick', 'serverTick', 'update', 'doUpdate'):

                    method_body = []
                    for stmt in node.body:
                        method_body.extend(translate_statement(stmt, 'this', 'namespace'))
                    return (node.name, '\n'.join(method_body))
    except Exception:
        pass
    return None

def generate_tick_handler_js(namespace: str, entity_id: str, tick_logic: str) -> list:
    lines = [
        f"world.afterEvents.entitySpawn.subscribe((e) => {{",
        f"    if (!e.entity.typeId.includes('{namespace}:{entity_id}')) return;",
        f"    const tick_id = setInterval(() => {{",
        f"        {tick_logic}",
        f"    }}, 50); // Bedrock tick = ~50ms in scripting API",
        f"    e.entity.onTickEventCalls = (e.entity.onTickEventCalls || 0) + 1;",
        f"}});",
    ]
    return lines
class JavaSymbolTable:


    JAVA_TYPE_TO_BEDROCK: Dict[str, str] = {
        'Player': 'Player', 'ServerPlayer': 'Player', 'LocalPlayer': 'Player',
        'Entity': 'Entity', 'LivingEntity': 'Entity', 'Mob': 'Entity',
        'PathfinderMob': 'Entity', 'Animal': 'Entity', 'Monster': 'Entity',
        'ItemStack': 'ItemStack', 'Item': 'ItemTypeStr',
        'BlockPos': 'Vector3', 'Vec3': 'Vector3', 'Vector3f': 'Vector3', 'Vec3i': 'Vector3',
        'BlockState': 'BlockPermutation',
        'Level': 'Dimension', 'ServerLevel': 'Dimension', 'World': 'Dimension',
        'Container': 'Container', 'Inventory': 'Container', 'SimpleContainer': 'Container',
        'AABB': 'BlockVolume', 'AxisAlignedBB': 'BlockVolume',
        'CompoundTag': 'DynamicProperties', 'CompoundNBT': 'DynamicProperties',
        'ListTag': 'DynamicArray', 'ResourceLocation': 'string',
        'int': 'number', 'float': 'number', 'double': 'number',
        'long': 'number', 'short': 'number', 'byte': 'number',
        'boolean': 'boolean', 'String': 'string', 'void': 'void',
    }


    TYPE_METHOD_MAP: Dict[str, Dict[str, str]] = {
        'Player': {
            'sendMessage':        '{0}.sendMessage({1})',
            'getHealth':          '{0}.getComponent("minecraft:health").currentValue',
            'setHealth':          '{0}.getComponent("minecraft:health").setCurrentValue({1})',
            'getMaxHealth':       '{0}.getComponent("minecraft:health").maxValue',
            'getInventory':       '{0}.getComponent("minecraft:inventory").container',
            'addItem':            '{0}.getComponent("minecraft:inventory").container.addItem({1})',
            'removeItem':         '{0}.getComponent("minecraft:inventory").container.removeItem({1})',
            'getLevel':           '{0}.dimension',
            'getPosition':        '{0}.location',
            'setPosition':        '{0}.teleport({1})',
            'isCreative':         '({0}.gameMode === GameMode.creative)',
            'isSpectator':        '({0}.gameMode === GameMode.spectator)',
            'isSprinting':        '{0}.isSprinting',
            'isOnGround':         '{0}.isOnGround',
            'getExperiencePoints': '{0}.getTotalXp()',
            'addExperiencePoints': '{0}.addExperience({1})',
            'hurt':               '{0}.applyDamage({1})',
            'heal':               '{0}.getComponent("minecraft:health").setCurrentValue({0}.getComponent("minecraft:health").currentValue + {1})',
            'getEffect':          '{0}.getEffect("{1}")',
            'addEffect':          '{0}.addEffect("{1}", {2}, {{ duration: {3} }})',
            'removeEffect':       '{0}.removeEffect("{1}")',
            'getName':            '{0}.nameTag',
        },
        'Entity': {
            'getHealth':    '{0}.getComponent("minecraft:health").currentValue',
            'setHealth':    '{0}.getComponent("minecraft:health").setCurrentValue({1})',
            'getMaxHealth': '{0}.getComponent("minecraft:health").maxValue',
            'getPosition':  '{0}.location',
            'setPosition':  '{0}.teleport({1})',
            'getVelocity':  '{0}.getVelocity()',
            'setVelocity':  '{0}.applyImpulse({1})',
            'kill':         '{0}.kill()',
            'remove':       '{0}.remove()',
            'hurt':         '{0}.applyDamage({1})',
            'isAlive':      '(!{0}.isRemoved())',
            'getType':      '{0}.typeId',
            'getTags':      '{0}.getTags()',
            'hasTag':       '{0}.hasTag({1})',
            'addTag':       '{0}.addTag({1})',
            'removeTag':    '{0}.removeTag({1})',
            'getLevel':     '{0}.dimension',
            'getCustomName':'{ 0}.nameTag',
            'setCustomName':'{0}.nameTag = {1}',
        },
        'ItemStack': {
            'getCount':       '{0}.amount',
            'setCount':       '{0}.amount = {1}',
            'grow':           '{0}.amount += {1}',
            'shrink':         '{0}.amount -= {1}',
            'isEmpty':        '({0}.amount <= 0)',
            'getItem':        '{0}.typeId',
            'getMaxStackSize':'{0}.maxAmount',
            'copy':           'new ItemStack({0}.typeId, {0}.amount)',
            'getDamageValue': '{0}.getComponent("minecraft:durability").damage',
            'setDamageValue': '{0}.getComponent("minecraft:durability").damage = {1}',
            'getDisplayName': '({0}.nameTag ?? {0}.typeId)',
            'setCustomName':  '{0}.nameTag = {1}',
        },
        'Dimension': {
            'setBlockState':       '{0}.getBlock({1}).setPermutation({2})',
            'getBlockState':       '{0}.getBlock({1}).permutation',
            'getBlockEntity':      '{0}.getBlock({1})',
            'addParticle':         '{0}.spawnParticle({1}, {2})',
            'playSound':           '{0}.playSound("{1}", {2})',
            'getEntitiesOfClass':  '[...{0}.getEntities({{ type: "{1}" }})]',
            'getClosestPlayer':    '{0}.getPlayers()[0]',
        },
        'DynamicProperties': {
            'getInt':     '({0}.getDynamicProperty({1}) ?? 0)',
            'putInt':     '{0}.setDynamicProperty({1}, {2})',
            'getFloat':   '({0}.getDynamicProperty({1}) ?? 0.0)',
            'putFloat':   '{0}.setDynamicProperty({1}, {2})',
            'getBoolean': '({0}.getDynamicProperty({1}) ?? false)',
            'putBoolean': '{0}.setDynamicProperty({1}, {2})',
            'getString':  '({0}.getDynamicProperty({1}) ?? "")',
            'putString':  '{0}.setDynamicProperty({1}, {2})',
            'hasKey':     '({0}.getDynamicProperty({1}) !== undefined)',
            'contains':   '({0}.getDynamicProperty({1}) !== undefined)',
            'remove':     '{0}.setDynamicProperty({1}, undefined)',
            'getCompound':'JSON.parse({0}.getDynamicProperty({1}) ?? "{{}}")',
            'put':        '{0}.setDynamicProperty({1}, JSON.stringify({2}))',
        },
        'Container': {
            'getItem':          '{0}.getItem({1})',
            'setItem':          '{0}.setItem({1}, {2})',
            'getContainerSize': '{0}.size',
            'addItem':          '{0}.addItem({1})',
        },
        'Vector3': {
            'add':        '{{ x: {0}.x+{1}.x, y: {0}.y+{1}.y, z: {0}.z+{1}.z }}',
            'subtract':   '{{ x: {0}.x-{1}.x, y: {0}.y-{1}.y, z: {0}.z-{1}.z }}',
            'scale':      '{{ x: {0}.x*{1}, y: {0}.y*{1}, z: {0}.z*{1} }}',
            'length':     'Math.sqrt({0}.x**2+{0}.y**2+{0}.z**2)',
            'distanceTo': 'Math.sqrt(({0}.x-{1}.x)**2+({0}.y-{1}.y)**2+({0}.z-{1}.z)**2)',
        },
    }

    _CAP_ENERGY    = {'receiveEnergy','extractEnergy','getEnergyStored','getMaxEnergyStored','canReceive','canExtract'}
    _CAP_FLUID     = {'fill','drain','getFluidAmount','getTankCapacity','getFluidInTank','getTanks','isFluidValid'}
    _CAP_ITEM_HDL  = {'insertItem','extractItem','getStackInSlot','getSlots','isItemValid','getSlotLimit'}
    _CAP_ITEMSTACK = {'getCount','setCount','grow','shrink','isEmpty'}

    def __init__(self):
        self.classes: Dict[str, Dict] = {}
        self.variables: Dict[str, str] = {}
        self.method_return_types: Dict[str, str] = {}
        self._qualifier_type_cache: Dict[str, str] = {}

    def register_class(self, class_name: str, superclass: Optional[str] = None, interfaces: List[str] = None):
        self.classes[class_name] = {
            'superclass': superclass,
            'interfaces': interfaces or [],
            'methods': {},
            'fields': {}
        }

    def register_method(self, class_name: str, method_name: str, return_type: str, params: Dict[str, str]):
        if class_name in self.classes:
            self.classes[class_name]['methods'][method_name] = {
                'return': return_type,
                'params': params
            }

    def register_field(self, class_name: str, field_name: str, field_type: str):
        if class_name in self.classes:
            self.classes[class_name]['fields'][field_name] = field_type

    def set_variable_type(self, var_name: str, var_type: str):
        self.variables[var_name] = var_type
        self._qualifier_type_cache[var_name] = self._resolve_bedrock_type(var_type)

    def get_variable_type(self, var_name: str) -> Optional[str]:
        return self.variables.get(var_name)

    def _resolve_bedrock_type(self, java_type: str) -> Optional[str]:
        base = re.sub(r'<.*>', '', java_type).strip()
        return self.JAVA_TYPE_TO_BEDROCK.get(base)

    def get_bedrock_type_for_var(self, var_name: str) -> Optional[str]:
        if var_name in self._qualifier_type_cache:
            return self._qualifier_type_cache[var_name]
        lower = var_name.lower()
        if lower in ('player', 'p', 'serverplayer', 'localplayer'): return 'Player'
        if lower in ('entity', 'mob', 'e', 'target', 'attacker', 'victim'): return 'Entity'
        if lower in ('stack', 'itemstack', 'item', 'helditem', 'mainhand', 'offhand'): return 'ItemStack'
        if lower in ('level', 'world', 'dimension', 'serverlevel', 'dim'): return 'Dimension'
        if lower in ('nbt', 'tag', 'compound', 'data', 'persistentdata'): return 'DynamicProperties'
        if lower in ('pos', 'blockpos', 'position', 'origin', 'loc', 'location'): return 'Vector3'
        if lower in ('inventory', 'container', 'inv', 'chest', 'slots'): return 'Container'
        return None

    def resolve_method_call(self, qualifier: str, method: str, args: List[str]) -> Optional[str]:
        btype = self.get_bedrock_type_for_var(qualifier)
        if not btype:
            return None
        template = self.TYPE_METHOD_MAP.get(btype, {}).get(method)
        if template is None:
            return None
        result = template.replace('{0}', qualifier)
        for i, arg in enumerate(args):
            result = result.replace(f'{{{i + 1}}}', arg)
        return result

    def method_belongs_to_capability(self, method_name: str) -> Optional[str]:
        if method_name in self._CAP_ENERGY:    return 'energy'
        if method_name in self._CAP_FLUID:     return 'fluid'
        if method_name in self._CAP_ITEM_HDL:  return 'item_handler'
        if method_name in self._CAP_ITEMSTACK: return 'itemstack'
        return None

    def scan_java_file(self, java_code: str):
        if JAVALANG_AVAILABLE:
            self._scan_ast(java_code)
        else:
            self._scan_regex(java_code)

    def _scan_ast(self, java_code: str):
        try:
            tree = javalang.parse.parse(java_code)
            for _, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    superclass = node.extends.name if node.extends else None
                    interfaces = [i.name for i in (node.implements or [])]
                    self.register_class(node.name, superclass, interfaces)
                    for method in node.methods:
                        ret_type = method.return_type.name if method.return_type else 'void'
                        params = {}
                        for p in (method.parameters or []):
                            ptype = p.type.name if hasattr(p.type, 'name') else str(p.type)
                            params[p.name] = ptype
                            self.set_variable_type(p.name, ptype)
                        self.register_method(node.name, method.name, ret_type, params)
                    for field in node.fields:
                        ftype = field.type.name if hasattr(field.type, 'name') else str(field.type)
                        for decl in field.declarators:
                            self.register_field(node.name, decl.name, ftype)
                            self.set_variable_type(decl.name, ftype)
                elif isinstance(node, javalang.tree.LocalVariableDeclaration):
                    ltype = node.type.name if hasattr(node.type, 'name') else str(node.type)
                    for decl in node.declarators:
                        self.set_variable_type(decl.name, ltype)
        except Exception:
            pass

    def _scan_regex(self, java_code: str):
        for m in re.finditer(r'class\s+(\w+)(?:\s+extends\s+(\w+))?', java_code):
            self.register_class(m.group(1), m.group(2))
        for m in re.finditer(
            r'(?:private|protected|public|final|static)\s+(?:final\s+)?(\w+(?:<[^>]+>)?)\s+(\w+)\s*[=;]',
            java_code
        ):
            self.set_variable_type(m.group(2), m.group(1))
        for m in re.finditer(r'(?:void|\w+)\s+\w+\s*\(([^)]+)\)', java_code):
            for param in m.group(1).split(','):
                parts = param.strip().split()
                if len(parts) >= 2:
                    self.set_variable_type(parts[-1].strip(), parts[-2].strip())

class MoLangBridge:


    _FUNC_MAP = [
        (r'Math\.sin\(', 'math.sin('),
        (r'Math\.cos\(', 'math.cos('),
        (r'Math\.tan\(', 'math.tan('),
        (r'Math\.asin\(', 'math.asin('),
        (r'Math\.acos\(', 'math.acos('),
        (r'Math\.atan2?\(', 'math.atan('),
        (r'Math\.sqrt\(', 'math.sqrt('),
        (r'Math\.abs\(', 'math.abs('),
        (r'Math\.floor\(', 'math.floor('),
        (r'Math\.ceil\(', 'math.ceil('),
        (r'Math\.round\(', 'math.round('),
        (r'Math\.min\(', 'math.min('),
        (r'Math\.max\(', 'math.max('),
        (r'Math\.clamp\(', 'math.clamp('),
        (r'Math\.pow\(([^,]+),\s*2\)', r'(\1 * \1)'),                        
        (r'Math\.pow\(([^,]+),\s*([^)]+)\)', r'math.pow(\1, \2)'),
        (r'Math\.PI', '3.14159265'),
        (r'Math\.toRadians\(([^)]+)\)', r'(\1 * 0.01745329)'),
        (r'Math\.toDegrees\(([^)]+)\)', r'(\1 * 57.2957795)'),
        (r'Math\.random\(\)', 'math.random(0, 1)'),
        (r'Math\.lerp\(([^,]+),\s*([^,]+),\s*([^)]+)\)', r'math.lerp(\1, \2, \3)'),
    ]


    _VAR_MAP = [
        (r'\bentity\.tickCount\b',           'query.anim_time * 20'),
        (r'\bthis\.tickCount\b',              'query.anim_time * 20'),
        (r'\btickCount\b',                     'query.anim_time * 20'),
        (r'\banimationTick\b',                 'query.anim_time * 20'),
        (r'\bpartialTick\b',                   'query.anim_time'),
        (r'\bentity\.isInWater\(\)\b',     'query.is_in_water'),
        (r'\bentity\.isOnGround\(\)\b',    'query.is_on_ground'),
        (r'\bentity\.isSprinting\(\)\b',   'query.is_sprinting'),
        (r'\bentity\.isSneaking\(\)\b',    'query.is_sneaking'),
        (r'\bentity\.isSwimming\(\)\b',    'query.is_swimming'),
        (r'\bentity\.isBaby\(\)\b',        'query.is_baby'),
        (r'\bentity\.isOnFire\(\)\b',      'query.is_on_fire'),
        (r'\bentity\.getHealth\(\)',         'query.health'),
        (r'\bentity\.getSpeed\(\)',          'query.ground_speed'),
        (r'\bentity\.xRot\b',                'query.body_x_rotation'),
        (r'\bentity\.yRot\b',                'query.body_y_rotation'),
        (r'\bthis\.(\w+)\b',                r'variable.\1'),
    ]


    _TERNARY_RE = re.compile(
        r'([^?]+)\?\s*([^:]+):\s*(.+)'
    )

    @staticmethod
    def java_to_molang(java_expr: str) -> str:
        m = java_expr.strip()

        m = re.sub(r'\((?:float|double|int|long)\)\s*', '', m)

        m = re.sub(r'^return\s+', '', m.strip())
        m = m.rstrip(';')

        tern = MoLangBridge._TERNARY_RE.match(m)
        if tern:
            cond = MoLangBridge.java_to_molang(tern.group(1).strip())
            t_val = MoLangBridge.java_to_molang(tern.group(2).strip())
            f_val = MoLangBridge.java_to_molang(tern.group(3).strip())
            return f'({cond} ? {t_val} : {f_val})'

        for pattern, replacement in MoLangBridge._FUNC_MAP:
            m = re.sub(pattern, replacement, m)

        for pattern, replacement in MoLangBridge._VAR_MAP:
            m = re.sub(pattern, replacement, m)

        m = re.sub(r'(\d+\.?\d*)f\b', r'\1', m)

        while '((' in m and '))' in m:
            m = re.sub(r'\(\(([^()]+)\)\)', r'(\1)', m)
        return m.strip()

    @staticmethod
    def build_animation_json_entry(bone: str, channel: str,
                                   java_expr: str, namespace: str) -> dict:
        molang = MoLangBridge.java_to_molang(java_expr)
        entry = {
            "0.0": {
                channel: [molang, "0.0", "0.0"]
                if channel != 'rotation' else [molang, "0.0", "0.0"]
            }
        }
        return entry

    @staticmethod
    def inject_molang_into_anim_file(anim_path: str, entity_name: str,
                                     bone_channel_map: Dict[str, Dict[str, str]]) -> None:
        if not os.path.exists(anim_path):
            return
        try:
            with open(anim_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception:
            return
        animations = data.get('animations', {})
        for anim_id, anim_body in animations.items():
            if entity_name not in anim_id:
                continue
            bones = anim_body.setdefault('bones', {})
            for bone, channels in bone_channel_map.items():
                bone_entry = bones.setdefault(bone, {})
                for ch, java_expr in channels.items():
                    molang = MoLangBridge.java_to_molang(java_expr)
                    bone_entry[ch] = molang
        with open(anim_path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2)


class AnimationControllerGenerator:

    @staticmethod
    def generate_default_controller(entity_name: str, animations: Dict[str, str]) -> dict:
        controller_name = f"controller.animation.{entity_name}.default"
        states = {
            "default": {
                "animations": list(animations.keys())[:1],                        
            }
        }

        for anim_name in list(animations.keys())[1:]:
            states[anim_name] = {
                "animations": [anim_name],
                "transitions": [{"default": "!variable.playing_" + anim_name}]
            }

        return {
            "format_version": "1.10.0",
            "animation_controllers": {
                controller_name: {
                    "states": states
                }
            }
        }


class NBTTranslator:

    NBT_TO_BEDROCK_MAP = {
        'readAdditionalSaveData': 'getDynamicProperty',
        'addAdditionalSaveData':  'setDynamicProperty',
        'getInt':    'getDynamicProperty', 'putInt':    'setDynamicProperty',
        'getString': 'getDynamicProperty', 'putString': 'setDynamicProperty',
        'getFloat':  'getDynamicProperty', 'putFloat':  'setDynamicProperty',
        'getBoolean':'getDynamicProperty', 'putBoolean':'setDynamicProperty',
        'getDouble': 'getDynamicProperty', 'putDouble': 'setDynamicProperty',
        'getLong':   'getDynamicProperty', 'putLong':   'setDynamicProperty',
        'getByte':   'getDynamicProperty', 'putByte':   'setDynamicProperty',
        'getList':   'getDynamicProperty', 'put':       'setDynamicProperty',
        'getCompound': 'getDynamicProperty',
    }


    _TYPE_HINTS = {
        'getInt': 'number', 'getFloat': 'number', 'getDouble': 'number',
        'getLong': 'number', 'getByte': 'number', 'getShort': 'number',
        'getString': 'string', 'getBoolean': 'boolean',
        'getList': 'array',   'getCompound': 'object',
    }

    @staticmethod
    def translate_nbt_call(method: str, args, namespace: str,
                           entity_var: str = 'entity') -> Optional[str]:
        bedrock = NBTTranslator.NBT_TO_BEDROCK_MAP.get(method)
        if bedrock is None:
            return None
        if not args:
            return None

        key_arg = None
        if JAVALANG_AVAILABLE:
            first = args[0]
            if isinstance(first, javalang.tree.Literal) and first.value.startswith('"'):
                key_arg = first.value.strip('"')
        if key_arg is None:

            m = re.search(r'"([^"]+)"', str(args))
            key_arg = m.group(1) if m else 'unknown'
        prop_key = f'"{namespace}:{key_arg}"'
        type_hint = NBTTranslator._TYPE_HINTS.get(method, 'any')
        default = {'number': 0, 'string': '""""', 'boolean': 'false',
                   'array': '[]', 'object': '{}'}.get(type_hint, 'null')
        if method.startswith('get') or method == 'readAdditionalSaveData':
            return f'    ({entity_var}.getDynamicProperty({prop_key}) ?? {default})'
        elif method.startswith('put') or method == 'addAdditionalSaveData':
            val_arg = 'value'
            if len(args) > 1 and JAVALANG_AVAILABLE:
                lit = args[1]
                if isinstance(lit, javalang.tree.Literal):
                    val_arg = lit.value
            return f'    {entity_var}.setDynamicProperty({prop_key}, {val_arg});'
        return None


class RecursiveNBTSerializer:


    _MAX_VALUE_LEN = 32_000

    @staticmethod
    def flatten(nbt: dict, prefix: str = '', depth: int = 0,
                _out: Optional[list] = None) -> list:
        if _out is None:
            _out = []
        if depth > 16:

            _out.append((prefix, json.dumps(nbt)[:RecursiveNBTSerializer._MAX_VALUE_LEN]))
            return _out
        for k, v in nbt.items():
            path = f'{prefix}.{k}' if prefix else k
            if isinstance(v, dict):
                RecursiveNBTSerializer.flatten(v, path, depth + 1, _out)
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    item_path = f'{path}.{i}'
                    if isinstance(item, dict):
                        RecursiveNBTSerializer.flatten(item, item_path, depth + 1, _out)
                    else:
                        _out.append((item_path, item))
            else:

                _out.append((path, v))
        return _out

    @staticmethod
    def emit_set_js(nbt: dict, namespace: str, entity_var: str = 'entity') -> list:
        lines = [f'// NBT serialization — {len(nbt)} top-level keys']
        pairs = RecursiveNBTSerializer.flatten(nbt)
        for dot_path, value in pairs:
            prop_key = f'{namespace}:{dot_path}'
            if isinstance(value, str):
                js_val = json.dumps(value)
            elif isinstance(value, bool):
                js_val = 'true' if value else 'false'
            elif value is None:
                js_val = 'null'
            else:
                js_val = str(value)
            if len(js_val) > RecursiveNBTSerializer._MAX_VALUE_LEN:
                js_val = json.dumps(js_val[:RecursiveNBTSerializer._MAX_VALUE_LEN])
            lines.append(f'{entity_var}.setDynamicProperty("{prop_key}", {js_val});')
        return lines

    @staticmethod
    def reconstruct_js(dot_paths: list, namespace: str,
                       entity_var: str = 'entity',
                       out_var: str = 'nbt') -> list:
        lines = [
            f'const {out_var} = {{}};',
            f'const _set = (obj, path, val) => {{',
            f'    const parts = path.split(".");',
            f'    let cur = obj;',
            f'    for (let i = 0; i < parts.length - 1; i++) {{',
            f'        const k = isNaN(parts[i]) ? parts[i] : +parts[i];',
            f'        if (cur[k] === undefined) cur[k] = isNaN(parts[i+1]) ? {{}} : [];',
            f'        cur = cur[k];',
            f'    }}',
            f'    cur[parts[parts.length-1]] = val;',
            f'}};',
        ]
        for path in dot_paths:
            prop_key = f'{namespace}:{path}'
            lines.append(
                f'_set({out_var}, "{path}", {entity_var}.getDynamicProperty("{prop_key}"));')
        lines.append(f'// {out_var} is now the reconstructed nested object')
        return lines

    @staticmethod
    def scan_and_emit_nbt_scripts(java_code: str, entity_id: str,
                                   namespace: str, bp_folder: str) -> None:
        safe = sanitize_identifier(entity_id.split(':')[-1])
        write_calls: list = []
        read_calls:  list = []


        save_body = _extract_method_body(java_code, 'addAdditionalSaveData')
        if save_body:
            for m in re.finditer(
                r'(?:tag|nbt|compound)\.(put\w+)\s*\(\s*"([^"]+)"\s*,\s*([^;)]+)',
                save_body
            ):
                method, key, val = m.group(1), m.group(2), m.group(3).strip()
                prop = f'{namespace}:{safe}.{key}'
                write_calls.append(f'entity.setDynamicProperty("{prop}", {val});')


        load_body = _extract_method_body(java_code, 'readAdditionalSaveData')
        if load_body:
            for m in re.finditer(
                r'(?:tag|nbt|compound)\.(get\w+)\s*\(\s*"([^"]+)"\)',
                load_body
            ):
                method, key = m.group(1), m.group(2)
                prop = f'{namespace}:{safe}.{key}'
                default = {'getInt':'0','getFloat':'0','getDouble':'0',
                           'getString':'\'\'','getBoolean':'false','getLong':'0'}.get(method, 'null')
                read_calls.append(
                    f'const {key} = entity.getDynamicProperty("{prop}") ?? {default};')

        if not write_calls and not read_calls:
            return

        lines = [
            f'import {{ world }} from "@minecraft/server";',
            '',
            f'// Auto-generated NBT serializer for {entity_id}',
            f'export function saveNBT_{safe}(entity) {{',
        ] + [f'    {l}' for l in write_calls] + [
            '}',
            '',
            f'export function loadNBT_{safe}(entity) {{',
        ] + [f'    {l}' for l in read_calls] + [
            '}',
            '',
        ]
        out_path = os.path.join(bp_folder, 'scripts', f'{safe}_nbt.js')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
        print(f'[nbt] Wrote {out_path}')


class CapabilityRegistry:

    CAPABILITY_TYPES = {
        'IEnergyStorage': {
            'properties': ['energy_stored', 'max_energy'],
            'methods': ['receiveEnergy', 'extractEnergy', 'getEnergyStored', 'getMaxEnergyStored'],
            'bedrock_type': 'number',
        },
        'IFluidHandler': {
            'properties': ['fluid_amount', 'fluid_type', 'fluid_capacity'],
            'methods': ['fill', 'drain', 'getFluidAmount', 'getTankCapacity'],
            'bedrock_type': 'compound',
        },
        'IItemHandler': {
            'properties': ['slot_contents', 'slot_count'],
            'methods': ['insertItem', 'extractItem', 'getStackInSlot', 'getSlots'],
            'bedrock_type': 'itemstack',
        },
    }

    @staticmethod
    def generate_capability_manager(capability_type: str, namespace: str, entity_id: str) -> list:
        lines = [
            'import { ItemStack } from "@minecraft/server";',
            "",
        ]

        if capability_type not in CapabilityRegistry.CAPABILITY_TYPES:
            return lines

        cap = CapabilityRegistry.CAPABILITY_TYPES[capability_type]

        lines.append(f"// {capability_type} Manager for {entity_id}")
        lines.append(f"const {entity_id}_capabilities = {{")

        for prop in cap['properties']:
            lines.append(f"    {prop}: 0,")

        lines.append(f"}};")
        lines.append("")


        for method in cap['methods']:
            if method.startswith('get'):
                prop_name = method[3:].lower()
                lines.append(f"function {entity_id}_{method}(entity) {{")
                lines.append(f'    return entity.getDynamicProperty("{namespace}:{entity_id}_{prop_name}") || 0;')
                lines.append(f"}}")
            elif method in ['receiveEnergy', 'fill']:
                lines.append(f"function {entity_id}_{method}(entity, amount) {{")
                lines.append(f'    const current = entity.getDynamicProperty("{namespace}:{entity_id}_stored") || 0;')
                lines.append(f'    const max = entity.getDynamicProperty("{namespace}:{entity_id}_max") || 1000;')
                lines.append(f"    const accepted = Math.min(amount, max - current);")
                lines.append(f'    entity.setDynamicProperty("{namespace}:{entity_id}_stored", current + accepted);')
                lines.append(f"    return accepted;")
                lines.append(f"}}")
            elif method in ['extractEnergy', 'drain']:
                lines.append(f"function {entity_id}_{method}(entity, amount) {{")
                lines.append(f'    const current = entity.getDynamicProperty("{namespace}:{entity_id}_stored") || 0;')
                lines.append(f"    const extracted = Math.min(amount, current);")
                lines.append(f'    entity.setDynamicProperty("{namespace}:{entity_id}_stored", current - extracted);')
                lines.append(f"    return extracted;")
                lines.append(f"}}")

        lines.append("")
        return lines

class EventRouter:


    FORGE_TO_BEDROCK: Dict[str, tuple] = {

        'LivingHurtEvent':                      ('entityHurt',                 'entity',  False),
        'LivingDamageEvent':                    ('entityHurt',                 'entity',  False),
        'LivingDeathEvent':                     ('entityDie',                  'entity',  False),
        'LivingKnockBackEvent':                 ('entityHurt',                 'entity',  True),

        'PlayerInteractEvent.RightClickEntity': ('playerInteractWithEntity',   'player',  True),
        'PlayerInteractEvent.RightClickBlock':  ('playerPlaceBlock',           'player',  True),
        'PlayerInteractEvent.LeftClickBlock':   ('playerBreakBlock',           'player',  True),
        'PlayerInteractEvent.LeftClickEmpty':   ('playerBreakBlock',           'player',  False),

        'BlockEvent.BreakEvent':                ('playerBreakBlock',           'player',  True),
        'BlockEvent.PlaceEvent':                ('playerPlaceBlock',           'player',  True),
        'BlockEvent.EntityPlaceEvent':          ('playerPlaceBlock',           'entity',  True),
        'BlockEvent.EntityMultiPlaceEvent':     ('playerPlaceBlock',           'entity',  True),

        'ItemPickupEvent':                      ('entityPickUpItem',           'entity',  False),
        'ItemTossEvent':                        ('entityDropItem',             'entity',  True),
        'AnvilRepairEvent':                     ('playerInteractWithEntity',   'player',  False),
        'PlayerDestroyItemEvent':               ('playerBreakBlock',           'player',  False),

        'EntityJoinWorldEvent':                 ('entitySpawn',                'entity',  False),
        'EntityJoinLevelEvent':                 ('entitySpawn',                'entity',  False),
        'EntityLeaveWorldEvent':                ('entityRemove',               'entity',  False),
        'EntityLeaveLevelEvent':                ('entityRemove',               'entity',  False),
        'EntityTeleportEvent':                  ('entityHitBlock',             'entity',  True),
        'EntityMountEvent':                     ('playerInteractWithEntity',   'player',  True),

        'PlayerLoggedInEvent':                  ('playerJoin',                 'player',  False),
        'PlayerLoggedOutEvent':                 ('playerLeave',                'player',  False),
        'PlayerChangedDimensionEvent':          ('playerDimensionChange',      'player',  False),
        'PlayerRespawnEvent':                   ('playerSpawn',                'player',  False),

        'TickEvent.ServerTickEvent':            ('worldInitialize',            None,      False),
        'TickEvent.ClientTickEvent':            ('tick',                       None,      False),
        'TickEvent.LevelTickEvent':             ('worldInitialize',            None,      False),
        'LevelTickEvent':                       ('worldInitialize',            None,      False),

        'ProjectileImpactEvent':                ('projectileHitBlock',         'entity',  False),
        'ArrowNockEvent':                       ('playerInteractWithEntity',   'player',  True),

        'ServerChatEvent':                      ('chatSend',                   'player',  True),
        'CommandEvent':                         ('chatSend',                   'player',  False),

        'ExplosionEvent.Detonate':              ('explosion',                  None,      False),
        'FillBucketEvent':                      ('playerInteractWithBlock',    'player',  True),
    }


    _CANCEL_PATTERN = re.compile(
        r'event\.setCanceled\s*\(\s*true\s*\)|event\.isCanceled\s*\(\s*\)'
    )

    @staticmethod
    def generate_event_wrapper(forge_event: str, java_logic: str,
                                namespace: str, symbol_table=None) -> list:
        lines: list = []
        mapping = EventRouter.FORGE_TO_BEDROCK.get(forge_event)
        if mapping is None:

            safe = re.sub(r'[^\w]', '_', forge_event).lower()
            lines.append(f'// TODO: No Bedrock equivalent for Forge event: {forge_event}')
            lines.append(f'// Original Java handler body preserved below as reference:')
            for line in java_logic.splitlines():
                lines.append(f'//   {line}')
            lines.append('')
            return lines

        bedrock_event, entity_param, use_before = mapping
        bus = 'beforeEvents' if use_before else 'afterEvents'


        if EventRouter._CANCEL_PATTERN.search(java_logic):
            bus = 'beforeEvents'

        if bedrock_event == 'worldInitialize':
            lines.append(f'world.afterEvents.worldInitialize.subscribe((e) => {{')
        else:
            lines.append(f'world.{bus}.{bedrock_event}.subscribe((e) => {{')
            if entity_param:
                lines.append(f'    const {entity_param} = e.{entity_param};')


        translated = re.sub(
            r'event\.setCanceled\s*\(\s*true\s*\)',
            'e.cancel()',
            java_logic
        )
        lines.append(translated)
        lines.append('});')
        lines.append('')
        return lines

    @staticmethod
    def scan_and_emit_all_handlers(java_code: str, namespace: str,
                                    safe_name: str, symbol_table=None) -> list:
        all_lines: list = []

        handler_re = re.compile(
            r'@SubscribeEvent[\s\S]*?public\s+\w+\s+(\w+)\s*\(\s*(\w+)(?:\.[\w.]+)?\s+\w+\s*\)',
            re.MULTILINE
        )
        for m in handler_re.finditer(java_code):
            method_name = m.group(1)
            event_type  = m.group(2)

            body_start = java_code.find('{', m.end())
            if body_start == -1:
                continue
            depth, i = 0, body_start
            while i < len(java_code):
                if java_code[i] == '{'  : depth += 1
                elif java_code[i] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            body = java_code[body_start + 1: i].strip()
            all_lines += EventRouter.generate_event_wrapper(
                event_type, body, namespace, symbol_table
            )
        return all_lines

class MathTranspiler:

    @staticmethod
    def transpile_vector_op(java_expr: str) -> str:

        bedrock = re.sub(r'new Vector3d\(([^,]+),\s*([^,]+),\s*([^)]+)\)', r'new Vector3(\1, \2, \3)', java_expr)

        bedrock = re.sub(r'(\w+)\.add\((\w+)\)', r'{ x: \1.x + \2.x, y: \1.y + \2.y, z: \1.z + \2.z }', bedrock)

        bedrock = re.sub(r'(\w+)\.subtract\((\w+)\)', r'{ x: \1.x - \2.x, y: \1.y - \2.y, z: \1.z - \2.z }', bedrock)

        bedrock = re.sub(r'(\w+)\.scale\(([^)]+)\)', r'{ x: \1.x * \2, y: \1.y * \2, z: \1.z * \2 }', bedrock)

        bedrock = re.sub(r'\.getX\(\)', '.x', bedrock)
        bedrock = re.sub(r'\.getY\(\)', '.y', bedrock)
        bedrock = re.sub(r'\.getZ\(\)', '.z', bedrock)

        bedrock = re.sub(r'new AxisAlignedBB\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)', 
                         r'new BlockVolume({ min: { x: \1, y: \2, z: \3 }, max: { x: \4, y: \5, z: \6 } })', bedrock)
        return bedrock

    @staticmethod
    def transpile_math_expr(java_expr: str) -> str:
        bedrock = java_expr.replace('Math.PI', 'Math.PI')
        bedrock = bedrock.replace('Math.sqrt', 'Math.sqrt')
        bedrock = bedrock.replace('Math.pow', 'Math.pow')
        bedrock = bedrock.replace('Math.random', 'Math.random')
        bedrock = re.sub(r'Math\.toRadians\(([^)]+)\)', r'(\1) * Math.PI / 180', bedrock)
        bedrock = re.sub(r'Math\.toDegrees\(([^)]+)\)', r'(\1) * 180 / Math.PI', bedrock)
        return bedrock


class JavaToBedrockMethodMap:

    STRICT_MAPPING = {

        'world.setBlockState': 'dimension.getBlock({0}).setPermutation({1})',
        'world.getBlockState': 'dimension.getBlock({0}).permutation',
        'world.getBlockEntity': 'dimension.getBlock({0})',
        'level.setBlockState': 'dimension.getBlock({0}).setPermutation({1})',


        'entity.getHealth': 'entity.getComponent("health").currentValue',
        'entity.setHealth': 'entity.getComponent("health").setCurrentValue({0})',
        'entity.getMaxHealth': 'entity.getComponent("health").maxValue',
        'entity.getPosition': 'entity.location',
        'entity.setPosition': 'entity.teleport({0})',
        'entity.getVelocity': 'entity.velocity',
        'entity.setVelocity': 'entity.applyImpulse({0})',
        'entity.kill': 'entity.kill()',


        'player.sendMessage': 'player.sendMessage({0})',
        'player.getInventory': 'player.getComponent("minecraft:inventory")',
        'player.addItem': 'player.getComponent("minecraft:inventory").container.addItem({0})',
        'player.removeItem': 'player.getComponent("minecraft:inventory").container.removeItem({0})',


        'itemStack.getTag': 'itemStack.getComponent("minecraft:enchantable")',
        'compoundTag.getInt': 'entity.getDynamicProperty({0}) || 0',
        'compoundTag.putInt': 'entity.setDynamicProperty({0}, {1})',


        'new ItemStack': 'new ItemStack({0})',
        'itemStack.getCount': 'itemStack.amount',
        'itemStack.setCount': 'itemStack.amount = {0}',


        'world.addParticle': 'dimension.spawnParticle({0}, {1})',
        'world.playSound': 'dimension.playSound({0}, {1})',
    }

    @staticmethod
    def lookup_method(java_method: str) -> Optional[str]:
        bedrock = JavaToBedrockMethodMap.STRICT_MAPPING.get(java_method)
        if bedrock is None:
            log_critical_failure(f"No Bedrock equivalent for Java method: {java_method}")
        return bedrock

    @staticmethod
    def translate_method_call(java_method: str, args: list, qualifier: Optional[str] = None) -> Optional[str]:
        template = JavaToBedrockMethodMap.lookup_method(java_method)
        if not template:
            return None


        translated_args = [translate_expression(arg) for arg in args]


        for i, arg in enumerate(translated_args):
            template = template.replace(f'{{{i}}}', arg)


        return template


class TickRegistry:

    def __init__(self):
        self.tick_handlers: Dict[str, list] = {}
        self.tick_priority: Dict[str, int] = {}

    def register_tick_handler(self, entity_id: str, logic: str, priority: int = 100):
        if entity_id not in self.tick_handlers:
            self.tick_handlers[entity_id] = []
        self.tick_handlers[entity_id].append(logic)
        self.tick_priority[entity_id] = priority

    def generate_central_tick_loop(self, namespace: str) -> list:
        lines = [
            'import { world, system } from "@minecraft/server";',
            "",
            "// Central Tick Registry - Prevents Script Watchdog Timeout",
            "const tick_registry = {",
            "    handlers: {},",
            "    max_ms_per_tick: 10, // 10ms max per tick",
            "};",
            "",
            "system.runInterval(() => {",
            "    const start_time = Date.now();",
            "    const active_entities = world.getDimension('minecraft:overworld').getEntities({",
            "        tags: ['mod:needs_tick']",
            "    });",
            "",
            "    for (const entity of active_entities) {",
            "        if (Date.now() - start_time > tick_registry.max_ms_per_tick) break;",
            "        const handler_id = entity.typeId;",
            "        if (tick_registry.handlers[handler_id]) {",
            "            try {",
            "                tick_registry.handlers[handler_id](entity);",
            "            } catch (e) {",
            "                console.error(`Tick error for ${handler_id}: ${e.message}`);",
            "            }",
            "        }",
            "    }",
            "}, 1); // Run every game tick",
            "",
        ]


        for entity_id, handlers in self.tick_handlers.items():
            lines.append(f"tick_registry.handlers['{namespace}:{entity_id}'] = (entity) => {{")
            for handler in handlers:
                lines.extend(handler.split('\n'))
            lines.append("};")
            lines.append("")

        return lines


class ComponentUIBridge:

    @staticmethod
    def detect_container_class(java_code: str) -> Optional[Dict[str, str]]:
        if 'class ' not in java_code or 'Container' not in java_code:
            return None

        container_info = {
            'class_name': '',
            'slots': [],
            'buttons': [],
            'fields': []
        }


        match = re.search(r'class\s+(\w+)\s+extends\s+Container', java_code)
        if match:
            container_info['class_name'] = match.group(1)


        slot_pattern = r'this\.addSlotToContainer\s*\(\s*new\s+Slot\s*\(([^)]+)\)'
        for match in re.finditer(slot_pattern, java_code):
            container_info['slots'].append(match.group(1))


        button_pattern = r'new\s+GuiButton\s*\(\s*(\d+),\s*([^,]+),\s*([^,]+),\s*"([^"]+)"'
        for match in re.finditer(button_pattern, java_code):
            container_info['buttons'].append({
                'id': match.group(1),
                'x': match.group(2),
                'y': match.group(3),
                'label': match.group(4)
            })

        return container_info if container_info['class_name'] else None

    @staticmethod
    def generate_action_form(container_info: Dict[str, str]) -> list:
        lines = [
            f"// Container → UI Form: {container_info['class_name']}",
            "const show_container_form = async (player) => {",
            "    const form = new ActionFormData();",
            f"    form.title('{container_info['class_name']}');",
            "    ",
        ]

        for button in container_info.get('buttons', []):
            lines.append(f"    form.button('{button['label']}');")

        lines.extend([
            "    ",
            "    const response = await form.show(player);",
            "    if (response.canceled) return;",
            "    ",
            "    switch (response.selection) {",
        ])

        for i, button in enumerate(container_info.get('buttons', [])):
            lines.append(f"        case {i}:")
            lines.append(f"            handle_container_action_{button['id']}(player);")
            lines.append(f"            break;")

        lines.extend([
            "    }",
            "};",
            "",
        ])

        return lines


class JavaGUIConverter:


    _GUI_BASES = {
        'Screen', 'AbstractContainerScreen', 'GuiScreen',
        'AbstractGui', 'ContainerScreen', 'ChestScreen',
    }

    @staticmethod
    def is_gui_class(java_code: str) -> bool:
        return bool(re.search(
            r'extends\s+(?:' + '|'.join(JavaGUIConverter._GUI_BASES) + r')',
            java_code
        ))

    @staticmethod
    def extract_gui_info(java_code: str) -> Dict:
        info: Dict = {
            'class_name': '',
            'title':      None,
            'width':      176,
            'height':     166,
            'slots':      [],
            'buttons':    [],
            'labels':     [],
            'text_fields':[],
        }

        cm = re.search(r'class\s+(\w+)\s+extends', java_code)
        if cm:
            info['class_name'] = cm.group(1)


        for w_pat in [r'imageWidth\s*=\s*(\d+)', r'xSize\s*=\s*(\d+)']:
            wm = re.search(w_pat, java_code)
            if wm:
                info['width'] = int(wm.group(1))
                break
        for h_pat in [r'imageHeight\s*=\s*(\d+)', r'ySize\s*=\s*(\d+)']:
            hm = re.search(h_pat, java_code)
            if hm:
                info['height'] = int(hm.group(1))
                break


        tm = re.search(r'super\s*\([^,]*Component\.translatable\s*\("([^"]+)"\)', java_code)
        if tm:
            info['title'] = tm.group(1)


        for sm in re.finditer(
            r'addSlot\s*\(\s*new\s+\w*Slot\s*\([^,]+,\s*(\d+),\s*(\d+),\s*(\d+)\)',
            java_code
        ):
            info['slots'].append({
                'index': int(sm.group(1)),
                'x':     int(sm.group(2)),
                'y':     int(sm.group(3)),
            })


        for bm in re.finditer(
            r'addRenderableWidget\s*\([^;]*Button\s*\.\s*builder\s*\(Component\.translatable\s*\("([^"]+)"\)[^)]*\)'
            r'|addButton\s*\(\s*new\s+\w*Button\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*"([^"]+)"',
            java_code
        ):
            label = bm.group(1) or bm.group(6) or 'Button'
            x = int(bm.group(2)) if bm.group(2) else 0
            y = int(bm.group(3)) if bm.group(3) else 0
            w = int(bm.group(4)) if bm.group(4) else 80
            h = int(bm.group(5)) if bm.group(5) else 20
            info['buttons'].append({'label': label, 'x': x, 'y': y, 'w': w, 'h': h})


        for tfm in re.finditer(
            r'new\s+(?:EditBox|TextField)\s*\([^)]*\)',
            java_code
        ):
            info['text_fields'].append({'hint': 'text_input'})


        for lm in re.finditer(
            r'drawString\s*\([^,]*,\s*"([^"]+)"',
            java_code
        ):
            info['labels'].append({'text': lm.group(1)})

        return info

    @staticmethod
    def generate_variables_grid_json(gui_info: Dict, namespace: str) -> dict:
        slots = gui_info.get('slots', [])
        if not slots:
            return {}
        grid_items = []
        for slot in slots:
            grid_items.append({
                'type': 'slot',
                'index': slot['index'],
                'offset': [slot['x'] - gui_info['width'] // 2,
                             slot['y'] - gui_info['height'] // 2, 0],
            })
        return {
            'namespace': namespace,
            f'{gui_info["class_name"]}_grid': {
                'type':   'grid',
                'grid_dimensions': {'x': len(slots), 'y': 1},
                'grid_item_template': f'{namespace}.{gui_info["class_name"]}_slot',
                'collection_name': f'{namespace}_container',
                'grid_rescaling_type': 'none',
                '__items__': grid_items,
            },
        }

    @staticmethod
    def generate_controls_json(gui_info: Dict, namespace: str) -> dict:
        controls = {}
        for i, btn in enumerate(gui_info.get('buttons', [])):
            key = f'{sanitize_identifier(btn["label"])}_button_{i}'
            controls[key] = {
                'type':        'button',
                'text':        btn['label'],
                'size':        [btn['w'], btn['h']],
                'offset':      [btn['x'], btn['y']],
                'button_mappings': [],
            }
        for i, lbl in enumerate(gui_info.get('labels', [])):
            key = f'label_{i}'
            controls[key] = {
                'type':    'label',
                'text':    lbl['text'],
                'offset':  [0, i * 10],
                'color':   [0.2, 0.2, 0.2, 1.0],
            }
        return {'namespace': namespace, 'controls': controls}

    @staticmethod
    def generate_modal_form_js(gui_info: Dict, namespace: str) -> list:
        cls = gui_info['class_name']
        safe = sanitize_identifier(cls)
        title = gui_info.get('title') or cls
        lines = [
            f'// GUI Form: {cls} → Bedrock ModalFormData',
            f'import {{ world }} from "@minecraft/server";',
            f'import {{ ModalFormData, ActionFormData }} from "@minecraft/server-ui";',
            '',
            f'export async function show_{safe}_form(player) {{',
        ]
        has_text = bool(gui_info.get('text_fields'))
        has_btns = bool(gui_info.get('buttons'))
        if has_text:
            lines.append(f'    const form = new ModalFormData();')
            lines.append(f'    form.title("{title}");')
            for i, tf in enumerate(gui_info['text_fields']):
                lines.append(f'    form.textField("Field {i}", "Enter value");')
            lines += [
                f'    const res = await form.show(player);',
                f'    if (res.canceled) return;',
                f'    const [{ ", ".join(f"field{i}" for i in range(len(gui_info["text_fields"]))) }] = res.formValues;',
            ]
        elif has_btns:
            lines.append(f'    const form = new ActionFormData();')
            lines.append(f'    form.title("{title}");')
            for btn in gui_info['buttons']:
                lines.append(f'    form.button("{btn["label"]}");')
            lines += [
                f'    const res = await form.show(player);',
                f'    if (res.canceled) return;',
                f'    switch (res.selection) {{',
            ]
            for i, btn in enumerate(gui_info['buttons']):
                fn = sanitize_identifier(btn['label'])
                lines += [
                    f'        case {i}: handle_{safe}_{fn}(player); break;',
                ]
            lines.append(f'    }}')
        else:
            lines.append(f'    // No interactive components detected — check PORTING_NOTES')
        lines += [f'}}', '']
        return lines

    @staticmethod
    def process(java_code: str, namespace: str, out_rp: str, out_bp_scripts: str) -> None:
        if not JavaGUIConverter.is_gui_class(java_code):
            return
        gui_info = JavaGUIConverter.extract_gui_info(java_code)
        if not gui_info['class_name']:
            return
        safe = sanitize_identifier(gui_info['class_name'])

        grid = JavaGUIConverter.generate_variables_grid_json(gui_info, namespace)
        if grid:
            grid_path = os.path.join(out_rp, 'ui', f'{safe}_grid.json')
            os.makedirs(os.path.dirname(grid_path), exist_ok=True)
            with open(grid_path, 'w', encoding='utf-8') as fh:
                json.dump(grid, fh, indent=2)

        ctrl = JavaGUIConverter.generate_controls_json(gui_info, namespace)
        ctrl_path = os.path.join(out_rp, 'ui', f'{safe}_controls.json')
        os.makedirs(os.path.dirname(ctrl_path), exist_ok=True)
        with open(ctrl_path, 'w', encoding='utf-8') as fh:
            json.dump(ctrl, fh, indent=2)

        js_lines = JavaGUIConverter.generate_modal_form_js(gui_info, namespace)
        js_path = os.path.join(out_bp_scripts, f'ui_{safe}.js')
        os.makedirs(os.path.dirname(js_path), exist_ok=True)
        with open(js_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(js_lines))
        print(f'[gui] {gui_info["class_name"]} → {safe}_controls.json + ui_{safe}.js')


class DependencyRegistry:

    def __init__(self):
        self.scripts: Dict[str, Dict] = {}
        self.nbt_properties: Dict[str, Set[str]] = {}
        self.dynamic_props: Dict[str, Set[str]] = {}
        self.tick_entities: Set[str] = set()
        self.capabilities: Dict[str, str] = {}

    def register_script(self, script_id: str, depends_on: List[str] = None):
        self.scripts[script_id] = {'depends_on': depends_on or [], 'code': ''}

    def register_nbt_property(self, entity_id: str, prop_name: str):
        if entity_id not in self.nbt_properties:
            self.nbt_properties[entity_id] = set()
        self.nbt_properties[entity_id].add(prop_name)

    def register_dynamic_property(self, entity_id: str, prop_name: str):
        if entity_id not in self.dynamic_props:
            self.dynamic_props[entity_id] = set()
        self.dynamic_props[entity_id].add(prop_name)

    def mark_entity_for_ticking(self, entity_id: str):
        self.tick_entities.add(entity_id)


class GlobalCapabilityRegistry:

    @staticmethod
    def generate_registry_js(namespace: str) -> list:
        return [
            'import { world } from "@minecraft/server";',
            '',
            '// ── Global Capability Registry ────────────────────────────────────────────',
            '// Shared by all converted mods in this pack.  Keys are namespaced to avoid',
            '// collisions when multiple mods are loaded side-by-side.',
            '',
            'const _ns = (ns, key) => `${ns}:cap_${key}`;',
            '',
            'export const CapRegistry = {',
            '',
            '    // ── Energy ──────────────────────────────────────────────────────────',
            '    energy: {',
            '        /** Receive energy into entity up to maxCapacity RF/FE.  Returns accepted amount. */',
            '        receive(entity, ns, amount, maxCapacity = 1_000_000) {',
            '            const key = _ns(ns, "energy");',
            '            const cur = entity.getDynamicProperty(key) ?? 0;',
            '            const accepted = Math.min(amount, maxCapacity - cur);',
            '            entity.setDynamicProperty(key, cur + accepted);',
            '            return accepted;',
            '        },',
            '        extract(entity, ns, amount) {',
            '            const key = _ns(ns, "energy");',
            '            const cur = entity.getDynamicProperty(key) ?? 0;',
            '            const extracted = Math.min(amount, cur);',
            '            entity.setDynamicProperty(key, cur - extracted);',
            '            return extracted;',
            '        },',
            '        get(entity, ns) { return entity.getDynamicProperty(_ns(ns,"energy")) ?? 0; },',
            '        set(entity, ns, v){ entity.setDynamicProperty(_ns(ns,"energy"), v); },',
            '    },',
            '',
            '    // ── Fluid ───────────────────────────────────────────────────────────',
            '    fluid: {',
            '        fill(entity, ns, fluidId, amount, capacity = 1000) {',
            '            const amtKey  = _ns(ns, "fluid_amount");',
            '            const typeKey = _ns(ns, "fluid_type");',
            '            const curAmt  = entity.getDynamicProperty(amtKey) ?? 0;',
            '            const curType = entity.getDynamicProperty(typeKey) ?? fluidId;',
            '            if (curAmt > 0 && curType !== fluidId) return 0;',
            '            const filled  = Math.min(amount, capacity - curAmt);',
            '            entity.setDynamicProperty(amtKey,  curAmt + filled);',
            '            entity.setDynamicProperty(typeKey, fluidId);',
            '            return filled;',
            '        },',
            '        drain(entity, ns, amount) {',
            '            const amtKey = _ns(ns, "fluid_amount");',
            '            const cur    = entity.getDynamicProperty(amtKey) ?? 0;',
            '            const drained = Math.min(amount, cur);',
            '            entity.setDynamicProperty(amtKey, cur - drained);',
            '            return { amount: drained, type: entity.getDynamicProperty(_ns(ns,"fluid_type")) ?? "minecraft:water" };',
            '        },',
            '        getAmount(entity, ns){ return entity.getDynamicProperty(_ns(ns,"fluid_amount")) ?? 0; },',
            '        getType(entity,   ns){ return entity.getDynamicProperty(_ns(ns,"fluid_type"))   ?? "minecraft:water"; },',
            '    },',
            '',
            '    // ── Item slots ──────────────────────────────────────────────────────',
            '    item: {',
            '        /** Insert an ItemStack JSON into a named slot. */',
            '        insert(entity, ns, slotIndex, itemJson) {',
            '            const key = _ns(ns, `item_slot_${slotIndex}`);',
            '            if (entity.getDynamicProperty(key)) return false;',
            '            entity.setDynamicProperty(key, JSON.stringify(itemJson));',
            '            return true;',
            '        },',
            '        extract(entity, ns, slotIndex) {',
            '            const key  = _ns(ns, `item_slot_${slotIndex}`);',
            '            const raw  = entity.getDynamicProperty(key);',
            '            if (!raw) return null;',
            '            entity.setDynamicProperty(key, undefined);',
            '            return JSON.parse(raw);',
            '        },',
            '        get(entity, ns, slotIndex) {',
            '            const raw = entity.getDynamicProperty(_ns(ns,`item_slot_${slotIndex}`));',
            '            return raw ? JSON.parse(raw) : null;',
            '        },',
            '    },',
            '',
            '    // ── Cross-mod DynamicProperty sharing ──────────────────────────────',
            '    data: {',
            '        get(entity, ns, key)      { return entity.getDynamicProperty(_ns(ns, key)); },',
            '        set(entity, ns, key, val) { entity.setDynamicProperty(_ns(ns, key), val); },',
            '        has(entity, ns, key)      { return entity.getDynamicProperty(_ns(ns, key)) !== undefined; },',
            '        del(entity, ns, key)      { entity.setDynamicProperty(_ns(ns, key), undefined); },',
            '    },',
            '',
            '    // ── Registration (call from worldInitialize) ───────────────────────',
            '    registerProperties(propertyRegistry, ns, energyMax = 1_000_000) {',
            '        propertyRegistry.defineEntityNumberProperty(_ns(ns,"energy"),       0);',
            '        propertyRegistry.defineEntityNumberProperty(_ns(ns,"fluid_amount"), 0);',
            '        propertyRegistry.defineEntityStringProperty(_ns(ns,"fluid_type"),   "minecraft:water");',
            '    },',
            '',
            '};  // end CapRegistry',
            '',
            '// Auto-register on world init',
            f'world.afterEvents.worldInitialize.subscribe((e) => {{',
            f'    CapRegistry.registerProperties(e.propertyRegistry, "{namespace}");',
            f'}});',
            '',
        ]

    @staticmethod
    def write(namespace: str, bp_folder: str) -> None:
        out_path = os.path.join(bp_folder, 'scripts', 'cap_registry.js')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(GlobalCapabilityRegistry.generate_registry_js(namespace)))
        print(f'[cap_registry] Wrote {out_path}')

    @staticmethod
    def ensure_import_in_main(bp_folder: str) -> None:
        main_path = os.path.join(bp_folder, 'scripts', 'main.js')
        import_line = 'import "./cap_registry.js";\n'
        if os.path.exists(main_path):
            with open(main_path, 'r', encoding='utf-8') as fh:
                content = fh.read()
            if 'cap_registry' not in content:
                with open(main_path, 'w', encoding='utf-8') as fh:
                    fh.write(import_line + content)
        else:
            with open(main_path, 'w', encoding='utf-8') as fh:
                fh.write(import_line)


def log_critical_failure(message: str):
    porting_notes_path = os.path.join(BP_FOLDER, "PORTING_NOTES.txt")
    with open(porting_notes_path, "a", encoding="utf-8") as f:
        f.write(f"CRITICAL FAILURE: {message}\n")

OUTPUT_DIR = "Bedrock_Pack"
BP_FOLDER = os.path.join(OUTPUT_DIR, "bp")
RP_FOLDER = os.path.join(OUTPUT_DIR, "rp")
BP_RP_FORMAT_VERSION = "1.21.0"
RP_LEGACY_RENDER_FORMAT = "1.10.0"
RP_LEGACY_ANIM_FORMAT = "1.10.0"
VALID_ICON_SIZES = [2, 4, 8, 16, 32, 64, 128, 256]
JAVA_GOAL_PRIORITIES = {
    "FloatGoal": 0, "SwimGoal": 0, "BreatheAirGoal": 0,
    "NearestAttackableTargetGoal": 1, "NearestAttackableTargetExpiringGoal": 1,
    "ToggleableNearestAttackableTargetGoal": 1, "NonTamedTargetGoal": 1,
    "DefendVillageTargetGoal": 1, "HurtByTargetGoal": 2,
    "OwnerHurtByTargetGoal": 2, "OwnerHurtTargetGoal": 2, "ResetAngerGoal": 2,
    "MeleeAttackGoal": 3, "OcelotAttackGoal": 3, "CreeperSwellGoal": 3,
    "RangedAttackGoal": 3, "RangedBowAttackGoal": 3, "RangedCrossbowAttackGoal": 3,
    "LeapAtTargetGoal": 4, "MoveTowardsTargetGoal": 4,
    "AvoidEntityGoal": 5, "PanicGoal": 5, "RunAroundLikeCrazyGoal": 5,
    "FleeSunGoal": 5, "RestrictSunGoal": 5,
    "OpenDoorGoal": 6, "InteractDoorGoal": 6, "BreakDoorGoal": 6,
    "BreakBlockGoal": 6, "UseItemGoal": 6,
    "FollowOwnerGoal": 7, "FollowParentGoal": 7, "FollowMobGoal": 7,
    "FollowBoatGoal": 7, "FollowSchoolLeaderGoal": 7, "LlamaFollowCaravanGoal": 7,
    "LandOnOwnersShoulderGoal": 7, "MoveToBlockGoal": 7,
    "MoveTowardsRestrictionGoal": 7, "MoveThroughVillageGoal": 7,
    "MoveThroughVillageAtNightGoal": 7, "MoveTowardsRaidGoal": 7,
    "ReturnToVillageGoal": 7, "PatrolVillageGoal": 7, "FindWaterGoal": 7,
    "SitWhenOrderedToGoal": 7, "SitGoal": 7,
    "BreedGoal": 8, "TemptGoal": 8, "EatGrassGoal": 8, "BegGoal": 8,
    "TradeWithPlayerGoal": 8, "LookAtCustomerGoal": 8, "ShowVillagerFlowerGoal": 8,
    "TriggerSkeletonTrapGoal": 8, "DolphinJumpGoal": 8, "JumpGoal": 8,
    "CatLieOnBedGoal": 8, "CatSitOnBlockGoal": 8,
    "WaterAvoidingRandomStrollGoal": 8, "RandomWalkingGoal": 8,
    "RandomSwimmingGoal": 8, "RandomStrollGoal": 8,
    "LookAtGoal": 9, "LookAtPlayerGoal": 9, "LookAtWithoutMovingGoal": 9,
    "LookRandomlyGoal": 10, "RandomLookAroundGoal": 10,
}
COLLECTED_SOUND_DEFS: Dict[str, dict] = {}
_ENTITY_SOUND_EVENTS: Dict[str, dict] = {}
def ensure_dirs():
    rp_subs = [
        "textures",
        "textures/blocks",
        "textures/items",
        "textures/entity",
        "sound",
        "sounds",
        "models",
        "animations",
        "items",
        "entity",
        "render_controllers",
        "geometry",
        "lang",
        "assets",
        "misc",
        "biome_modifiers"
    ]
    bp_subs = [
        "entities",
        "items",
        "blocks",
        "functions",
        "scripts",
        "animations",
        "data",
        "recipes",
        "loot_tables"
    ]
    for folder, subs in [(RP_FOLDER, rp_subs), (BP_FOLDER, bp_subs)]:
        os.makedirs(folder, exist_ok=True)
        for s in subs:
            os.makedirs(os.path.join(folder, s), exist_ok=True)
def create_manifest(pack_name: str, pack_type: str, has_scripting: bool = False):
    manifest = {
        "format_version": 2,
        "header": {
            "name": pack_name,
            "description": f"{pack_name} converted pack",
            "uuid": str(uuid.uuid4()),
            "version": [1, 0, 0],
            "min_engine_version": [1, 21, 0]
        },
        "modules": [
            {
                "type": "resources" if pack_type == "RP" else "data",
                "uuid": str(uuid.uuid4()),
                "version": [1, 0, 0]
            }
        ]
    }
    if has_scripting and pack_type == "BP":
        manifest["modules"].append({
            "type": "script",
            "language": "javascript",
            "uuid": str(uuid.uuid4()),
            "version": [1, 0, 0],
            "entry": "scripts/main.js"
        })
        manifest["capabilities"] = ["scripting"]
    return manifest
def write_manifest_for(folder: str, pack_name: str, pack_type: str):
    path = os.path.join(folder, "manifest.json")
    os.makedirs(folder, exist_ok=True)
    scripts_dir = os.path.join(folder, "scripts")
    has_scripting = pack_type == "BP" and os.path.isdir(scripts_dir) and any(f.endswith(".js") for f in os.listdir(scripts_dir))
    manifest = create_manifest(pack_name, pack_type, has_scripting)
    if has_scripting:
        entry_scripts = [
            f for f in os.listdir(scripts_dir)
            if f.endswith(".js") and f != "main.js"
        ]
        main_js = os.path.join(scripts_dir, "main.js")
        if entry_scripts and not os.path.exists(main_js):
            imports = "\n".join(f'import "./{f}";' for f in sorted(entry_scripts))
            with open(main_js, "w", encoding="utf-8") as mf:
                mf.write(imports + "\n")
        manifest["dependencies"] = [
                {
                    "module_name": "@minecraft/server",
                    "version": "1.13.0"
                }
            ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
def sanitize_identifier(name: Optional[str]) -> str:
    if not name:
        return ""
    s = str(name).strip().lower()

    s = ''.join('_' if c.isspace() else c for c in s)

    s = ''.join(c if c.isalnum() or c in '._' else '_' for c in s)

    while '__' in s:
        s = s.replace('__', '_')

    while '..' in s:
        s = s.replace('..', '.')
    s = s.strip('._')
    return s
def sanitize_filename_keep_ext(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    base_s = base.lower()

    base_s = base_s.replace(' ', '_').replace('-', '_')

    base_s = ''.join(c if c.isalnum() or c in '._' else '_' for c in base_s)

    while '__' in base_s:
        base_s = base_s.replace('__', '_')
    base_s = base_s.strip('._')
    ext_s = ext.lower()
    return base_s + ext_s
    return base_s + ext_s
def build_geometry_id(namespace: Optional[str], name: str) -> str:
    n = sanitize_identifier(name)
    if namespace:
        ns = sanitize_identifier(namespace)
        if ns:
            return f"geometry.{ns}.{n}"
    return f"geometry.{n}"
def safe_write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
def find_jar_file(search_dir=".") -> Optional[str]:
    SKIP_SUFFIXES = ("-sources.jar", "-javadoc.jar", "-api.jar", "-slim.jar", "-dev.jar")
    candidates = []
    for f in os.listdir(search_dir):
        if not f.endswith(".jar"):
            continue
        if any(f.lower().endswith(s) for s in SKIP_SUFFIXES):
            print(f"Skipping auxiliary JAR file: {f}")
            continue
        candidates.append(os.path.join(search_dir, f))
    if not candidates:
        return None
    if len(candidates) > 1:
        print(f"Warning: Multiple JAR files found: {[os.path.basename(c) for c in candidates]}")
        print(f"Using: {os.path.basename(candidates[0])}. Move others out of this directory if incorrect.")
    return candidates[0]
def detect_loader_from_jar(jar_path: str) -> str:
    try:
        with zipfile.ZipFile(jar_path, 'r') as jar:
            names_lower = [n.lower() for n in jar.namelist()]
            if any("meta-inf/neoforge.mods.toml" in n for n in names_lower):
                return "neoforge"
            if any("meta-inf/mods.toml" in n for n in names_lower):
                return "forge"
            if any("fabric.mod.json" in n for n in names_lower):
                return "fabric"
            if any("quilt.mod.json" in n for n in names_lower):
                return "quilt"
    except Exception:
        pass
    return "unknown"
def _extract_first_logo_from_jar_legacy(jar_path: str) -> Optional[str]:
    temp_dir = ".temp_logo_extract"
    try:
        with zipfile.ZipFile(jar_path, 'r') as jar:
            for file in jar.namelist():
                if file.lower().endswith("logo.png"):
                    jar.extract(file, temp_dir)
                    return os.path.join(temp_dir, file)
    except Exception:
        pass
    return None
def sanitize_path_parts(path_str: str) -> List[str]:
    parts = path_str.replace("\\", "/").split("/")
    if not parts:
        return []
    sanitized = []
    for p in parts[:-1]:
        sanitized.append(sanitize_identifier(p) or "_")
    sanitized.append(sanitize_filename_keep_ext(parts[-1]))
    return sanitized
def _normalize_texture_subfolder(token: str) -> str:
    token = token.lower()
    if token in ("block", "blocks", "blockstate", "blockstates"):
        return "blocks"
    if token in ("item", "items"):
        return "items"
    if token in ("entity", "entities", "mob", "mobs"):
        return "entity"
    return token
def _read_json_from_jar(jar, file_path: str) -> Optional[dict]:
    try:
        with jar.open(file_path) as fh:
            raw = fh.read().decode('utf-8')
            return json.loads(raw)
    except Exception:
        return None
def copy_assets_from_jar(jar_path: str, resource_pack: str):
    global COLLECTED_SOUND_DEFS
    with zipfile.ZipFile(jar_path, 'r') as jar:
        for file in jar.namelist():
            normalized = file.replace("\\", "/")
            lower_file = normalized.lower()
            try:
                if lower_file.endswith(".png") and "/textures/" in lower_file:
                    parts = normalized.split('/')
                    try:
                        idx = [p.lower() for p in parts].index("textures")
                        after = parts[idx + 1:]
                    except ValueError:
                        after = parts[-1:]
                    if after:
                        first = after[0].lower()
                        category = _normalize_texture_subfolder(first)
                        if len(after) > 1:
                            dest_dir = os.path.join(resource_pack, "textures", category, *[sanitize_identifier(p) for p in after[1:-1]])
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_name = sanitize_filename_keep_ext(after[-1])
                            dest = os.path.join(dest_dir, dest_name)
                        else:
                            dest_dir = os.path.join(resource_pack, "textures", category)
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_name = sanitize_filename_keep_ext(after[0])
                            dest = os.path.join(dest_dir, dest_name)
                    else:
                        dest = os.path.join(resource_pack, "textures", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue
                if lower_file.endswith(".png"):
                    dest = os.path.join(resource_pack, "textures", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)

                    mcmeta_file = file + '.mcmeta'
                    try:
                        with jar.open(mcmeta_file) as mcmeta_src:
                            mcmeta_data = json.load(mcmeta_src)
                            if 'animation' in mcmeta_data:
                                anim = mcmeta_data['animation']
                                frames = anim.get('frames', [])
                                if isinstance(frames, list) and frames:

                                    if all(isinstance(f, int) for f in frames):
                                        frame_list = frames
                                    else:
                                        frame_list = [f['index'] if isinstance(f, dict) and 'index' in f else i for i, f in enumerate(frames)]
                                    flipbook_entry = {
                                        "flipbook_texture": dest.replace(resource_pack + '/', '').replace('\\', '/'),
                                        "atlas_tile": dest.replace(resource_pack + '/', '').replace('\\', '/').replace('.png', ''),
                                        "ticks_per_frame": anim.get('frametime', 1),
                                        "frames": frame_list if len(frame_list) > 1 and frame_list != list(range(len(frame_list))) else len(frame_list)
                                    }
                                    _RP_ASSET_INDEX["flipbook_textures"][flipbook_entry["atlas_tile"]] = flipbook_entry
                    except:
                        pass
                    continue
                if lower_file.endswith(".ogg"):
                    dest = os.path.join(resource_pack, "sound", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue
                if lower_file.endswith(".geo.json") or lower_file.endswith(".geo"):
                    dest_geo = os.path.join(resource_pack, "geometry", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest_geo), exist_ok=True)
                    with jar.open(file) as src_file, open(dest_geo, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    dest_model = os.path.join(resource_pack, "models", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest_model), exist_ok=True)
                    with jar.open(file) as src_file, open(dest_model, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue
                if (lower_file.endswith(".json") and "/models/" in lower_file) or lower_file.endswith(".geo.json"):
                    dest = os.path.join(resource_pack, "models", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    if lower_file.endswith(".json") and "/models/" in lower_file and not lower_file.endswith(".geo.json"):
                        try_convert_model_from_jar(jar, file, resource_pack)
                    continue
                if lower_file.endswith(".json") and "/animations/" in lower_file:
                    dest = os.path.join(resource_pack, "animations", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue
                if lower_file.endswith(".json"):
                    if os.path.basename(lower_file) in ("sounds.json", "sound_definitions.json") or                        (os.path.basename(lower_file).startswith("sounds") and lower_file.endswith(".json") and "/sounds/" in lower_file):
                        j = _read_json_from_jar(jar, file)
                        if isinstance(j, dict):
                            defs = j.get("sound_definitions", j) if isinstance(j.get("sound_definitions"), dict) else j
                            for k, v in defs.items():
                                if not isinstance(v, dict):
                                    continue
                                bare_k = k.split(":")[-1]
                                clean_k = sanitize_sound_key(bare_k)
                                if clean_k not in COLLECTED_SOUND_DEFS:
                                    cleaned = _sanitize_sound_def(v)
                                    if not cleaned.get("sounds"):
                                        cleaned["sounds"] = [{"name": f"sound/{clean_k}"}]
                                    COLLECTED_SOUND_DEFS[clean_k] = cleaned
                        continue
                    if "/data/" in lower_file:
                        sub = normalized.split("/data/", 1)[1]
                        parts = sanitize_path_parts(sub)
                        dest = os.path.join(BP_FOLDER, *parts)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with jar.open(file) as src_file, open(dest, "wb") as out_file:
                            shutil.copyfileobj(src_file, out_file)
                        continue
                    if "/assets/" in lower_file:
                        sub = normalized.split("/assets/", 1)[1]
                        parts_raw = sub.split("/")
                        sub_after = "/".join(parts_raw[1:]) if len(parts_raw) > 1 else sub
                        lower_after = sub_after.lower()
                        if "/sounds/" in lower_after or os.path.basename(lower_after).startswith("sounds") or os.path.basename(lower_after) == "sounds.json":
                            j = _read_json_from_jar(jar, file)
                            if isinstance(j, dict):
                                defs = j.get("sound_definitions", j) if isinstance(j.get("sound_definitions"), dict) else j
                                for k, v in defs.items():
                                    if not isinstance(v, dict):
                                        continue
                                    bare_k = k.split(":")[-1]
                                    clean_k = sanitize_sound_key(bare_k)
                                    if clean_k not in COLLECTED_SOUND_DEFS:
                                        cleaned = _sanitize_sound_def(v)
                                        if not cleaned.get("sounds"):
                                            cleaned["sounds"] = [{"name": f"sound/{clean_k}"}]
                                        COLLECTED_SOUND_DEFS[clean_k] = cleaned
                            continue
                        if "/lang/" in lower_after or lower_after.startswith("lang"):
                            if "/lang/" in lower_after:
                                after = sub_after.split("/lang/", 1)[1]
                            else:
                                after = os.path.basename(sub_after)
                            dest = os.path.join(resource_pack, "lang", sanitize_filename_keep_ext(os.path.basename(after)))
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with jar.open(file) as src_file, open(dest, "wb") as out_file:
                                shutil.copyfileobj(src_file, out_file)
                            continue
                        fname_base = os.path.basename(lower_after)
                        if any(seg in lower_after for seg in ("/blockstates/", "/models/block/", "/models/item/")):
                            continue
                        if fname_base in ("axe.json", "shovel.json", "sword.json", "pickaxe.json",
                                          "hoe.json", "bow.json", "crossbow.json", "trident.json"):
                            continue
                        if "biome_modifier" in fname_base or "biome_modifier" in lower_after:
                            continue
                        if "/neoforge/" in lower_after:
                            continue
                        if "/recipes/" in lower_after or fname_base.endswith("_recipe.json") or fname_base.endswith("_recipes.json"):
                            continue
                        if fname_base.endswith('.json') and len(fname_base) == 7 and fname_base[2] == '_' and fname_base[:2].islower() and fname_base[3:5].islower():
                            dest = os.path.join(resource_pack, "lang", sanitize_filename_keep_ext(fname_base))
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with jar.open(file) as src_file, open(dest, "wb") as out_file:
                                shutil.copyfileobj(src_file, out_file)
                            continue
                        j = _read_json_from_jar(jar, file)
                        if isinstance(j, dict):
                            if "minecraft:item" in j or ("item" in j and isinstance(j.get("item"), dict)):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                if not destname.endswith(".item.json"):
                                    destname = os.path.splitext(destname)[0] + ".item.json"
                                dest = os.path.join(resource_pack, "items", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            if "minecraft:block" in j or ("block" in j and isinstance(j.get("block"), dict)):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(BP_FOLDER, "blocks", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            if "minecraft:client_entity" in j or "minecraft:entity" in j:
                                destname = sanitize_identifier(os.path.splitext(os.path.basename(file))[0]) + ".entity.json"
                                dest = os.path.join(resource_pack, "entity", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            if "recipe" in os.path.basename(file).lower() or "recipe" in lower_after or                                "recipes" in j or any("ingredient" in str(k).lower() for k in j.keys()):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(BP_FOLDER, "recipes", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            if "biome_modifier" in os.path.basename(file).lower() or                                "biome_modifier" in lower_after or                                any("biome" in str(k).lower() for k in j.keys()):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(BP_FOLDER, "data", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            if all(isinstance(v, str) for v in j.values()) and len(j) > 10:
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(resource_pack, "lang", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                        continue
                    continue
                continue
            except Exception as ex:
                print(f"Asset copy error: {file} -> {ex}")
def convert_vanilla_model_to_geckolib(classic: dict, model_name: str = "model") -> dict:
    try:
        bones = []
        elements = classic.get("elements", [])
        groups = classic.get("groups", [])
        tex_size = classic.get("texture_size", [16, 16])
        if not elements and not groups:
            raise ValueError("Model must contain either 'elements' or 'groups'")
        def extract_uv(element: dict) -> list:
            faces = element.get("faces", {})
            for face_name in ["north", "south", "east", "west", "up", "down"]:
                if face_name in faces:
                    face_data = faces[face_name]
                    uv = face_data.get("uv", [0, 0, 16, 16])
                    if isinstance(uv, list) and len(uv) >= 4:
                        return [float(uv[0]), float(uv[1])]
            return [0.0, 0.0]
        def convert_rotation(rot: dict) -> dict:
            if not isinstance(rot, dict):
                return {"x": 0, "y": 0, "z": 0}
            axis = rot.get("axis", "x")
            angle = rot.get("angle", 0)
            try:
                angle = float(angle)
            except (ValueError, TypeError):
                angle = 0
            rotation = {"x": 0, "y": 0, "z": 0}
            if axis in ["x", "y", "z"]:
                rotation[axis] = angle
            return rotation
        def element_to_cube(el: dict) -> dict:
            if not isinstance(el, dict) or "from" not in el or "to" not in el:
                raise ValueError(f"Invalid element structure: {el}")
            from_pos = el["from"]
            to_pos = el["to"]
            if not (isinstance(from_pos, list) and isinstance(to_pos, list) and
                    len(from_pos) >= 3 and len(to_pos) >= 3):
                raise ValueError(f"Invalid from/to coordinates in element: {el}")
            cube = {
                "origin": [float(from_pos[0]) - 8, float(from_pos[1]), float(from_pos[2]) - 8],
                "size": [float(to_pos[0]) - float(from_pos[0]),
                        float(to_pos[1]) - float(from_pos[1]),
                        float(to_pos[2]) - float(from_pos[2])],
                "uv": extract_uv(el),
            }
            if "rotation" in el:
                cube["rotation"] = convert_rotation(el["rotation"])
            return cube
        def process_group(group, parent_pivot=[0, 0, 0]):
            if isinstance(group, int):
                if 0 <= group < len(elements):
                    bone = {
                        "name": f"bone_{group}",
                        "pivot": [0.0, 0.0, 0.0],
                        "cubes": [element_to_cube(elements[group])],
                    }
                    bones.append(bone)
                return
            if not isinstance(group, dict):
                return
            group_name = group.get("name", "bone")
            origin = group.get("origin", [0, 0, 0])
            if not isinstance(origin, list) or len(origin) < 3:
                origin = [0, 0, 0]
            pivot = [float(origin[0]) - 8, float(origin[1]), float(origin[2]) - 8]
            bone = {
                "name": group_name,
                "pivot": pivot,
                "cubes": [],
            }
            children = group.get("children", [])
            if not isinstance(children, list):
                children = []
            for child in children:
                if isinstance(child, int) and 0 <= child < len(elements):
                    bone["cubes"].append(element_to_cube(elements[child]))
                elif isinstance(child, dict):
                    process_group(child)
            if bone["cubes"]:
                bones.append(bone)
        if groups:
            for group in groups:
                process_group(group)
        else:
            root = {"name": "root", "pivot": [0.0, 0.0, 0.0], "cubes": []}
            for el in elements:
                try:
                    root["cubes"].append(element_to_cube(el))
                except ValueError as e:
                    print(f"Skipping invalid element: {e}")
                    continue
            if root["cubes"]:
                bones.append(root)
        if not bones:
            raise ValueError("No valid bones could be created from the model")
        if not isinstance(tex_size, list) or len(tex_size) < 2:
            tex_size = [16, 16]
        try:
            tex_width = int(tex_size[0])
            tex_height = int(tex_size[1])
        except (ValueError, TypeError):
            tex_width, tex_height = 16, 16
        return {
            "format_version": "1.12.0",
            "minecraft:geometry": [
                {
                    "description": {
                        "identifier": f"geometry.{model_name}",
                        "texture_width": tex_width,
                        "texture_height": tex_height,
                        "visible_bounds_width": 2,
                        "visible_bounds_height": 2,
                        "visible_bounds_offset": [0, 1, 0],
                    },
                    "bones": bones,
                }
            ],
        }
    except Exception as e:
        raise ValueError(f"Failed to convert vanilla model '{model_name}': {str(e)}") from e
def _extract_call_args(text: str, call_start: int, n_args: int) -> Optional[List[str]]:
    paren_pos = text.find('(', call_start)
    if paren_pos == -1:
        return None
    i = paren_pos + 1
    args: List[str] = []
    depth = 1
    buf: List[str] = []
    while i < len(text) and depth > 0:
        c = text[i]
        if c == '(':
            depth += 1
            buf.append(c)
        elif c == ')':
            depth -= 1
            if depth == 0:
                if len(args) < n_args:
                    args.append(''.join(buf).strip())
                break
            else:
                buf.append(c)
        elif c == ',' and depth == 1:
            if len(args) < n_args:
                args.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(c)
        i += 1
    return args if len(args) >= n_args else None
def _eval_rot_expr(expr: str) -> Optional[float]:
    s = expr.strip().rstrip('Ff ')
    s = s.replace('(float)', '').strip()
    s = s.replace('Math.PI', str(math.pi))
    try:
        val = float(s)
        return math.degrees(val)
    except (ValueError, TypeError):
        pass

    allowed_chars = set('0123456789.+-*/() ')
    if not all(c in allowed_chars for c in s):
        return None
    try:
        val = eval(s)
        return math.degrees(val)
    except Exception:
        pass
    return None
def _extract_method_body(java_code: str, method_names: List[str]) -> Optional[str]:
    if not JAVALANG_AVAILABLE:

        for name in method_names:
            idx = java_code.find(f' {name}(')
            if idx == -1:
                continue
            start = java_code.find('{', idx)
            if start == -1:
                continue
            depth, i = 0, start
            while i < len(java_code):
                if java_code[i] == '{':
                    depth += 1
                elif java_code[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return java_code[start:i + 1]
                i += 1
        return None
    ast = JavaAST(java_code)
    for name in method_names:
        body = ast.method_body_source(name)
        if body:
            return body
    return None
def convert_layerdefinition_to_geckolib(
    java_code: str,
    model_name: str,
    namespace: str,
    entity_name: Optional[str] = None,
) -> Optional[dict]:
    try:
        if not isinstance(java_code, str) or not java_code.strip():
            return None
        if 'LayerDefinition' not in java_code and 'MeshDefinition' not in java_code:
            return None
        LAYER_METHOD_NAMES = [
            'createBodyLayer', 'createBodyModel', 'createMeshes', 'createLayers',
            'createLayer', 'createModel', 'createModelData', 'bakeRoot',
        ]
        body = _extract_method_body(java_code, LAYER_METHOD_NAMES)
        if body is None:
            if 'addOrReplaceChild' not in java_code:
                return None
            body = java_code
        tex_w, tex_h = 64, 32
        idx = body.find('LayerDefinition.create(')
        if idx == -1:
            idx = java_code.find('LayerDefinition.create(')
        if idx != -1:
            start = idx + len('LayerDefinition.create(')
            comma1 = java_code.find(',', start)
            if comma1 != -1:
                comma2 = java_code.find(',', comma1 + 1)
                if comma2 != -1:
                    try:
                        tex_w = int(java_code[comma1 + 1:comma2].strip())
                        comma3 = java_code.find(',', comma2 + 1)
                        if comma3 != -1:
                            tex_h = int(java_code[comma2 + 1:comma3].strip())
                    except (ValueError, IndexError):
                        pass
        root_var = 'partdefinition'
        idx = body.find(' = ')
        if idx != -1:
            end = body.find('.getRoot()', idx)
            if end != -1:
                var_part = body[max(0, idx-20):idx].strip()
                eq_idx = var_part.rfind(' ')
                if eq_idx != -1:
                    root_var = var_part[eq_idx+1:].strip()
        var_to_bone: Dict[str, dict] = {
            root_var: {'name': '__root__', 'pivot': [0.0, 0.0, 0.0], 'rotation': [0.0, 0.0, 0.0], 'cubes': []}
        }
        var_to_parent_var: Dict[str, str] = {}
        start_pos = 0
        while True:
            idx = body.find(' = ', start_pos)
            if idx == -1:
                break
            idx2 = body.find('.addOrReplaceChild(', idx)
            if idx2 == -1:
                start_pos = idx + 1
                continue
            var_part = body[max(0, idx-20):idx].strip()
            eq_idx = var_part.rfind(' ')
            if eq_idx == -1:
                start_pos = idx + 1
                continue
            var_name = var_part[eq_idx+1:].strip()
            parent_part = body[idx:idx2].strip()
            eq_idx2 = parent_part.find(' = ')
            if eq_idx2 == -1:
                start_pos = idx + 1
                continue
            parent_var_part = parent_part[max(0, eq_idx2-20):eq_idx2].strip()
            sp_idx = parent_var_part.rfind(' ')
            if sp_idx == -1:
                parent_var = parent_var_part
            else:
                parent_var = parent_var_part[sp_idx+1:].strip()
            paren_start = idx2 + len('.addOrReplaceChild(')
            depth, i = 0, paren_start
            while i < len(body):
                if body[i] == '(':
                    depth += 1
                elif body[i] == ')':
                    depth -= 1
                    if depth == 0:
                        args_content = body[paren_start:i]
                        break
                i += 1
            else:
                start_pos = idx + 1
                continue
            var_name = cs.group(1)
            parent_var = cs.group(2)
            try:
                paren_start = body.index('(', cs.end() - 1)
            except ValueError:
                continue
            depth, i = 0, paren_start
            while i < len(body):
                if body[i] == '(':
                    depth += 1
                elif body[i] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            args_content = body[paren_start + 1:i]
            bone_name = var_name
            quote1 = args_content.find('"')
            if quote1 != -1:
                quote2 = args_content.find('"', quote1 + 1)
                if quote2 != -1:
                    bone_name = args_content[quote1+1:quote2]
            pivot = [0.0, 0.0, 0.0]
            rotation = [0.0, 0.0, 0.0]
            offset_idx = args_content.find('PartPose.offset(')
            if offset_idx != -1:
                offset_args = _extract_call_args(args_content, offset_idx, 3)
                if offset_args:
                    for idx, arg in enumerate(offset_args):
                        v = _parse_java_float(arg.strip())
                        if v is not None:
                            pivot[idx] = v
            rot_idx = args_content.find('PartPose.offsetAndRotation(')
            if rot_idx != -1:
                rot_args = _extract_call_args(args_content, rot_idx, 6)
                if rot_args and len(rot_args) >= 6:
                    for idx in range(3):
                        v = _parse_java_float(rot_args[idx].strip())
                        if v is not None:
                            pivot[idx] = v
                    for idx in range(3, 6):
                        deg = _eval_rot_expr(rot_args[idx].strip())
                        if deg is not None:
                            rotation[idx - 3] = round(deg, 4)
            cubes: list = []
            cur_u, cur_v = 0, 0
            tex_start = 0
            while True:
                tex_idx = args_content.find('.texOffs(', tex_start)
                if tex_idx == -1:
                    break
                tex_args = _extract_call_args(args_content, tex_idx, 2)
                if tex_args and len(tex_args) >= 2:
                    try:
                        cur_u = int(tex_args[0].strip())
                        cur_v = int(tex_args[1].strip())
                    except (ValueError, IndexError):
                        pass
                add_idx = args_content.find('.addBox(', tex_idx)
                if add_idx != -1:
                    add_args = _extract_call_args(args_content, add_idx, 6)
                    if add_args and len(add_args) >= 6:
                        try:
                            vals = [float(add_args[k].strip().rstrip('Ff')) for k in range(6)]
                            cubes.append({
                                "origin": [pivot[0]+vals[0], pivot[1]+vals[1], pivot[2]+vals[2]],
                                "size":   vals[3:6],
                                "uv":     [cur_u, cur_v],
                            })
                        except (ValueError, TypeError, IndexError):
                            pass
                tex_start = tex_idx + 1
            add_start = 0
            while True:
                add_idx = args_content.find('.addBox(', add_start)
                if add_idx == -1:
                    break
                add_args = _extract_call_args(args_content, add_idx, 6)
                if add_args and len(add_args) >= 6:
                    try:
                        vals = [float(add_args[k].strip().rstrip('Ff')) for k in range(6)]
                        candidate = {
                            "origin": [pivot[0]+vals[0], pivot[1]+vals[1], pivot[2]+vals[2]],
                            "size":   vals[3:6],
                            "uv":     [cur_u, cur_v],
                        }
                        if candidate not in cubes:
                            cubes.append(candidate)
                    except (ValueError, TypeError, IndexError):
                        pass
                add_start = add_idx + 1
            var_to_bone[var_name] = {
                'name': bone_name, 'pivot': pivot, 'rotation': rotation, 'cubes': cubes,
            }
            var_to_parent_var[var_name] = parent_var
            start_pos = idx + 1
        def _abs_pivot(var: str) -> List[float]:
            if var not in var_to_parent_var:
                return var_to_bone.get(var, {}).get('pivot', [0.0, 0.0, 0.0])

            path = []
            current = var
            visited = set()
            while current in var_to_parent_var and current not in visited:
                if current == root_var:
                    break
                visited.add(current)
                path.append(current)
                current = var_to_parent_var[current]
                if len(path) > 100:                
                    break
            if current == root_var:

                abs_pivot = [0.0, 0.0, 0.0]
                for v in reversed(path):
                    rel = var_to_bone[v]['pivot']
                    abs_pivot = [abs_pivot[i] + rel[i] for i in range(3)]
                return abs_pivot
            else:
                return var_to_bone.get(var, {}).get('pivot', [0.0, 0.0, 0.0])
        gecko_bones = []
        for var, bone in var_to_bone.items():
            if bone['name'] == '__root__':
                continue
            abs_piv = _abs_pivot(var)
            fixed_cubes = []
            for cube in bone['cubes']:
                rel = [cube['origin'][k] - bone['pivot'][k] for k in range(3)]
                fixed_cubes.append({
                    "origin": [round(abs_piv[k] + rel[k], 4) for k in range(3)],
                    "size":   cube['size'],
                    "uv":     cube['uv'],
                })
            b: dict = {"name": bone['name'], "pivot": [round(x, 4) for x in abs_piv]}
            if any(r != 0.0 for r in bone['rotation']):
                b["rotation"] = [round(r, 4) for r in bone['rotation']]
            pv2 = var_to_parent_var.get(var)
            if pv2 and pv2 != root_var and pv2 in var_to_bone:
                pbn = var_to_bone[pv2]['name']
                if pbn != '__root__':
                    b["parent"] = pbn
            if fixed_cubes:
                b["cubes"] = fixed_cubes
            gecko_bones.append(b)
        if not gecko_bones:
            return None
        geo_id = (
            f"geometry.{sanitize_identifier(namespace)}"
            f".{sanitize_identifier(entity_name or model_name)}"
        )
        return {
            "format_version": "1.12.0",
            "minecraft:geometry": [{
                "description": {
                    "identifier":            geo_id,
                    "texture_width":         tex_w,
                    "texture_height":        tex_h,
                    "visible_bounds_width":  2,
                    "visible_bounds_height": 2,
                    "visible_bounds_offset": [0, 1, 0],
                },
                "bones": gecko_bones,
            }],
        }
    except Exception as e:
        print(f"Failed to convert LayerDefinition model '{model_name}': {str(e)}")
        return None
def try_convert_model_from_jar(jar, file_path: str, resource_pack: str) -> bool:
    try:
        with jar.open(file_path) as fh:
            data = json.loads(fh.read().decode("utf-8"))
    except Exception:
        return False
    if "elements" not in data and "groups" not in data:
        return False
    model_name = sanitize_identifier(os.path.splitext(os.path.basename(file_path))[0])
    try:
        geckolib_data = convert_vanilla_model_to_geckolib(data, model_name)
        validation_issues = validate_geckolib_geometry(geckolib_data, model_name)
        if validation_issues:
            print(f"Validation warnings for {model_name}:")
            for warning in validation_issues[:3]:
                print(f"       {warning}")
    except Exception as e:
        print(f"Failed to convert {file_path}: {e}")
        return False
    out_path = os.path.join(resource_pack, "geometry", f"{model_name}.geo.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    safe_write_json(out_path, geckolib_data)
    status_msg = f"Converted vanilla model to GeckoLib: {file_path} to {out_path}"
    if 'validation_issues' in locals() and validation_issues:
        status_msg += f"  ({len(validation_issues)} warnings)"
    print(status_msg)
    return True
def convert_modelbase_to_geckolib(
    java_code: str,
    model_name: str,
    namespace: str,
    entity_name: Optional[str] = None,
) -> Optional[dict]:
    try:
        if not isinstance(java_code, str) or not java_code.strip():
            return None
        if 'setRotationPoint' not in java_code and 'addBox' not in java_code:
            return None
        if 'addOrReplaceChild' in java_code and 'setRotationPoint' not in java_code:
            return None
        tex_w, tex_h = 64, 64
        for pat in [
            r'this\.texWidth\s*=\s*(\d+)',
            r'textureWidth\s*=\s*(\d+)',
            r'this\.xTexSize\s*=\s*(\d+)',
        ]:
            m = re.search(pat, java_code)
            if m:
                try:
                    tex_w = int(m.group(1))
                except (ValueError, IndexError):
                    pass
                break
        for pat in [
            r'this\.texHeight\s*=\s*(\d+)',
            r'textureHeight\s*=\s*(\d+)',
            r'this\.yTexSize\s*=\s*(\d+)',
        ]:
            m = re.search(pat, java_code)
            if m:
                try:
                    tex_h = int(m.group(1))
                except (ValueError, IndexError):
                    pass
                break
        ctor_body = None
        cls_name_for_ctor = extract_class_name(java_code)
        if cls_name_for_ctor:
            ctor_body = _extract_method_body(java_code, [cls_name_for_ctor])
        if not ctor_body:
            ctor_body = _extract_method_body(java_code,
                ['init', 'registerParts', 'buildModel', 'setupModel', 'defineModel'])
        if not ctor_body:
            ctor_body = java_code
        var_to_name: Dict[str, str] = {}
        for m in re.finditer(
            r'(?:this\.)?(\w+)\s*=\s*new\s+(?:AdvancedModelBox|ExtendedModelRenderer'
            r'|ModelBoxRenderer|CubeRenderer|AModelRenderer)\s*\([^,)]*,\s*["\']([^"\']+)["\']',
            ctor_body
        ):
            var_to_name[m.group(1)] = m.group(2)
        for m in re.finditer(
            r'(?:this\.)?(\w+)\s*=\s*new\s+(?:ModelRenderer|ModelPart)\s*\(',
            ctor_body
        ):
            vname = m.group(1)
            if vname not in var_to_name:
                var_to_name[vname] = vname
        for m in re.finditer(
            r'new\s+(?:AdvancedModelBox|ModelRenderer)\s*\(\s*this\s*,\s*["\']([^"\']+)["\']',
            ctor_body
        ):
            window = ctor_body[max(0, m.start()-80):m.start()]
            am = re.search(r'(?:this\.)?(\w+)\s*=\s*$', window.rstrip())
            if am:
                var_to_name[am.group(1)] = m.group(1)
        if not var_to_name:
            return None
        var_pivot:    Dict[str, List[float]] = {}
        var_rotation: Dict[str, List[float]] = {}
        var_cubes:    Dict[str, list]        = {}
        var_parent:   Dict[str, str]         = {}
        for var in var_to_name:
            pat_rp = (
                rf'(?:this\.)?{re.escape(var)}\.setRotationPoint\s*\('
                rf'\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*\)'
            )
            m = re.search(pat_rp, ctor_body)
            if m:
                try:
                    var_pivot[var] = [
                        _pjf(m.group(1)), _pjf(m.group(2)), _pjf(m.group(3))
                    ]
                except (ValueError, TypeError, IndexError):
                    var_pivot[var] = [0.0, 0.0, 0.0]
            else:
                var_pivot[var] = [0.0, 0.0, 0.0]
            rx, ry, rz = 0.0, 0.0, 0.0
            pat_sra = (
                rf'setRotationAngle\s*\(\s*(?:this\.)?{re.escape(var)}'
                rf'\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*\)'
            )
            m = re.search(pat_sra, ctor_body)
            if m:
                try:
                    rx = math.degrees(_pjf(m.group(1)))
                    ry = math.degrees(_pjf(m.group(2)))
                    rz = math.degrees(_pjf(m.group(3)))
                except (ValueError, TypeError, IndexError):
                    pass
            else:
                for axis, idx in (('X', 0), ('Y', 1), ('Z', 2)):
                    pat_ax = (
                        rf'(?:this\.)?{re.escape(var)}\.rotateAngle{axis}\s*=\s*({_FLOAT_EXPR_RE})'
                    )
                    am = re.search(pat_ax, ctor_body)
                    if am:
                        deg = _eval_rot_expr(am.group(1))
                        if deg is not None:
                            if idx == 0: rx = deg
                            elif idx == 1: ry = deg
                            else: rz = deg
            var_rotation[var] = [round(rx, 4), round(ry, 4), round(rz, 4)]
            cubes: list = []
            cur_u, cur_v = 0, 0
            uv_pats = [
                rf'(?:this\.)?{re.escape(var)}\.setTextureOffset\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)',
                rf'(?:this\.)?{re.escape(var)}\.texOffset\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)',
            ]
            for uv_pat in uv_pats:
                for uvm in re.finditer(uv_pat, ctor_body):
                    try:
                        cur_u = int(uvm.group(1))
                        cur_v = int(uvm.group(2))
                    except (ValueError, IndexError):
                        continue
                    after = ctor_body[uvm.end():uvm.end() + 300]
                    ab = re.match(
                        r'\s*(?:\.\s*)?addBox\s*\('
                        rf'\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})'
                        rf'\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})',
                        after
                    )
                    if ab:
                        try:
                            ox, oy, oz = _pjf(ab.group(1)), _pjf(ab.group(2)), _pjf(ab.group(3))
                            sx, sy, sz = _pjf(ab.group(4)), _pjf(ab.group(5)), _pjf(ab.group(6))
                            pivot = var_pivot.get(var, [0., 0., 0.])
                            cubes.append({
                                "origin": [round(pivot[0]+ox, 4), round(pivot[1]+oy, 4), round(pivot[2]+oz, 4)],
                                "size":   [sx, sy, sz],
                                "uv":     [cur_u, cur_v],
                            })
                        except (ValueError, TypeError, IndexError):
                            pass
            for ab in re.finditer(
                rf'(?:this\.)?{re.escape(var)}\.addBox\s*\('
                rf'\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})'
                rf'\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})\s*,\s*({_FLOAT_RE})',
                ctor_body
            ):
                try:
                    ox, oy, oz = _pjf(ab.group(1)), _pjf(ab.group(2)), _pjf(ab.group(3))
                    sx, sy, sz = _pjf(ab.group(4)), _pjf(ab.group(5)), _pjf(ab.group(6))
                    pivot = var_pivot.get(var, [0., 0., 0.])
                    candidate = {
                        "origin": [round(pivot[0]+ox, 4), round(pivot[1]+oy, 4), round(pivot[2]+oz, 4)],
                        "size":   [sx, sy, sz],
                        "uv":     [cur_u, cur_v],
                    }
                    if candidate not in cubes:
                        cubes.append(candidate)
                except (ValueError, TypeError, IndexError):
                    pass
            var_cubes[var] = cubes
        for m in re.finditer(
            r'(?:this\.)?(\w+)\.addChild\s*\(\s*(?:this\.)?(\w+)\s*\)',
            ctor_body
        ):
            parent_var = m.group(1)
            child_var  = m.group(2)
            if child_var in var_to_name and parent_var in var_to_name:
                var_parent[child_var] = parent_var
        all_children = set(var_parent.keys())
        def _abs_piv(var: str, depth: int = 0, visited: set = None) -> List[float]:
            if visited is None:
                visited = set()
            if var in visited or depth > 10:
                return var_pivot.get(var, [0., 0., 0.])
            visited.add(var)
            p = var_parent.get(var)
            if p is None or p == var or p not in var_to_name:
                visited.remove(var)
                return var_pivot.get(var, [0., 0., 0.])
            parent_abs = _abs_piv(p, depth + 1, visited)
            rel        = var_pivot.get(var, [0., 0., 0.])
            visited.remove(var)
            return [parent_abs[i] + rel[i] for i in range(3)]
        gecko_bones = []
        for var, bone_name in var_to_name.items():
            abs_piv = _abs_piv(var)
            pivot   = var_pivot.get(var, [0., 0., 0.])
            fixed_cubes = []
            for cube in var_cubes.get(var, []):
                rel = [cube['origin'][i] - pivot[i] for i in range(3)]
                fixed_cubes.append({
                    "origin": [round(abs_piv[i] + rel[i], 4) for i in range(3)],
                    "size":   cube['size'],
                    "uv":     cube['uv'],
                })
            b: dict = {
                "name":  bone_name,
                "pivot": [round(x, 4) for x in abs_piv],
            }
            rot = var_rotation.get(var, [0., 0., 0.])
            if any(r != 0. for r in rot):
                b["rotation"] = rot
            p_var = var_parent.get(var)
            if p_var and p_var in var_to_name:
                b["parent"] = var_to_name[p_var]
            if fixed_cubes:
                b["cubes"] = fixed_cubes
            gecko_bones.append(b)
        if not gecko_bones:
            return None
        geo_id = (
            f"geometry.{sanitize_identifier(namespace)}"
            f".{sanitize_identifier(entity_name or model_name)}"
        )
        return {
            "format_version": "1.12.0",
            "minecraft:geometry": [{
                "description": {
                    "identifier":            geo_id,
                    "texture_width":         tex_w,
                    "texture_height":        tex_h,
                    "visible_bounds_width":  2,
                    "visible_bounds_height": 2,
                    "visible_bounds_offset": [0, 1, 0],
                },
                "bones": gecko_bones,
            }],
        }
    except Exception as e:
        print(f"Failed to convert ModelBase model '{model_name}': {str(e)}")
        return None
_FLOAT_RE      = r'[-+]?[0-9]*\.?[0-9]+[FfDdLl]?'
_FLOAT_EXPR_RE = r'[-+]?(?:\(float\)\s*)?[A-Za-z0-9_.*+\-/()\s]+'
def _pjf(s: str) -> float:
    v = _parse_java_float(str(s).strip())
    return v if v is not None else 0.0
def validate_geckolib_geometry(geo_data: dict, model_name: str) -> List[str]:
    warnings = []
    try:
        if not isinstance(geo_data, dict):
            return ["Geometry data is not a dictionary"]
        if "minecraft:geometry" not in geo_data:
            return ["Missing 'minecraft:geometry' key"]
        geometries = geo_data.get("minecraft:geometry", [])
        if not isinstance(geometries, list) or not geometries:
            return ["'minecraft:geometry' is not a non-empty list"]
        geometry = geometries[0]
        if not isinstance(geometry, dict):
            return ["First geometry entry is not a dictionary"]
        desc = geometry.get("description", {})
        if not isinstance(desc, dict):
            warnings.append("Geometry description is not a dictionary")
        else:
            required_desc_fields = ["identifier", "texture_width", "texture_height"]
            for field in required_desc_fields:
                if field not in desc:
                    warnings.append(f"Missing required description field: {field}")
                elif not isinstance(desc[field], (str, int)):
                    warnings.append(f"Description field '{field}' has invalid type")
        bones = geometry.get("bones", [])
        if not isinstance(bones, list):
            return ["'bones' is not a list"]
        if not bones:
            warnings.append("No bones found in geometry")
        bone_names = set()
        for i, bone in enumerate(bones):
            if not isinstance(bone, dict):
                warnings.append(f"Bone {i} is not a dictionary")
                continue
            if "name" not in bone:
                warnings.append(f"Bone {i} missing 'name' field")
            else:
                name = bone["name"]
                if not isinstance(name, str):
                    warnings.append(f"Bone {i} 'name' is not a string")
                elif name in bone_names:
                    warnings.append(f"Duplicate bone name: {name}")
                else:
                    bone_names.add(name)
            if "pivot" not in bone:
                warnings.append(f"Bone '{bone.get('name', i)}' missing 'pivot' field")
            else:
                pivot = bone["pivot"]
                if not isinstance(pivot, list) or len(pivot) != 3:
                    warnings.append(f"Bone '{bone.get('name', i)}' 'pivot' is not a 3-element list")
                else:
                    for j, coord in enumerate(pivot):
                        if not isinstance(coord, (int, float)):
                            warnings.append(f"Bone '{bone.get('name', i)}' pivot[{j}] is not numeric")
            cubes = bone.get("cubes", [])
            if not isinstance(cubes, list):
                warnings.append(f"Bone '{bone.get('name', i)}' 'cubes' is not a list")
            else:
                for j, cube in enumerate(cubes):
                    if not isinstance(cube, dict):
                        warnings.append(f"Bone '{bone.get('name', i)}' cube {j} is not a dictionary")
                        continue
                    for field in ["origin", "size", "uv"]:
                        if field not in cube:
                            warnings.append(f"Bone '{bone.get('name', i)}' cube {j} missing '{field}' field")
                        elif not isinstance(cube[field], list) or len(cube[field]) != (3 if field != "uv" else 2):
                            warnings.append(f"Bone '{bone.get('name', i)}' cube {j} '{field}' has wrong format")
            parent = bone.get("parent")
            if parent is not None:
                if not isinstance(parent, str):
                    warnings.append(f"Bone '{bone.get('name', i)}' 'parent' is not a string")
                elif parent not in bone_names and parent != "__root__":
                    warnings.append(f"Bone '{bone.get('name', i)}' references unknown parent '{parent}'")
    except Exception as e:
        return [f"Validation failed with exception: {str(e)}"]
    return warnings
def safe_write_json(out_path: str, data: dict) -> None:
    try:
        model_name = os.path.splitext(os.path.basename(out_path))[0]
        warnings = validate_geckolib_geometry(data, model_name)
        if warnings:
            print(f"Validation warnings for {out_path}:")
            for warning in warnings[:5]:
                print(f"       {warning}")
            if len(warnings) > 5:
                print(f"       ... and {len(warnings) - 5} more warnings")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise IOError(f"Failed to write JSON to {out_path}: {str(e)}") from e
def scan_and_convert_layerdefinition_models(
    java_files: Dict[str, str],
    namespace: str,
) -> Dict[str, str]:
    model_names = [
        'EntityModel', 'HierarchicalModel', 'AgeableMobModel',
        'LayerDefinition', 'BookOpenModel', 'ArmedModel', 'HeadedModel', 'SkullModelBase',
        'AdvancedEntityModel', 'ExtendedEntityModel', 'CitadelEntityModel',
        'BipedModel', 'QuadrupedModel', 'AgeableModel',
        'GeoModel', 'GeoLayerRenderer',
        'TileEntitySpecialRenderer', 'BlockEntityRenderer',                           
        'Block'                               
    ]
    CTOR_SIGNALS = ('setRotationPoint', 'addBox', 'addChild', 'setTextureOffset',
                    'texOffset', 'rotateAngleX', 'rotateAngleY', 'rotateAngleZ',
                    'setRotationAngle', 'AdvancedModelBox', 'ModelRenderer')
    result: Dict[str, str] = {}
    converted = 0
    for path, code in java_files.items():
        fname = os.path.basename(path).lower()
        if any(k in fname for k in ('renderer', 'entity', 'layer', 'event',
                                     'handler', 'registry', 'screen', 'gui',
                                     'packet', 'provider', 'capability')):
            if 'Model' not in os.path.splitext(os.path.basename(path))[0]:
                continue
        is_layerdef   = ('LayerDefinition' in code or 'MeshDefinition' in code
                         or 'addOrReplaceChild' in code)
        is_ctor_model = any(sig in code for sig in CTOR_SIGNALS)
        if not is_layerdef and not is_ctor_model:
            continue
        extends_model = False
        idx = code.find('extends ')
        if idx != -1:
            end = code.find('{', idx)
            if end == -1:
                end = code.find(';', idx)
            if end != -1:
                extends_part = code[idx:end]
                extends_model = any(name in extends_part for name in model_names)
        if not extends_model:
            sig_count = sum(1 for s in CTOR_SIGNALS if s in code)
            if sig_count < 3:
                continue
        if ('GeoModel' in code or 'IAnimatable' in code
                or 'getModelResource' in code or 'getAnimationResource' in code):
            continue
        cls_name   = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
        model_stem = sanitize_identifier(cls_name)
        out_path   = os.path.join(RP_FOLDER, "geometry", f"{model_stem}.geo.json")
        if os.path.exists(out_path):
            try:
                with open(out_path, encoding='utf-8') as fh:
                    existing = json.load(fh)
                geos = existing.get('minecraft:geometry', [])
                if geos:
                    geo_id = (geos[0].get('description') or {}).get('identifier', '')
                    if geo_id:
                        result[cls_name] = geo_id
            except Exception:
                pass
            continue
        geo_data: Optional[dict] = None
        method_used = ''
        conversion_warnings = []
        if is_layerdef:
            geo_data = convert_layerdefinition_to_geckolib(code, cls_name, namespace)
            if geo_data:
                method_used = 'layerdef'
                validation_issues = validate_geckolib_geometry(geo_data, cls_name)
                if validation_issues:
                    conversion_warnings.extend(validation_issues)
        if geo_data is None and is_ctor_model:
            geo_data = convert_modelbase_to_geckolib(code, cls_name, namespace)
            if geo_data:
                method_used = 'modelbase'
                validation_issues = validate_geckolib_geometry(geo_data, cls_name)
                if validation_issues:
                    conversion_warnings.extend(validation_issues)
        if geo_data is None:
            continue
        try:
            os.makedirs(os.path.join(RP_FOLDER, "geometry"), exist_ok=True)
            safe_write_json(out_path, geo_data)
            geo_id = geo_data['minecraft:geometry'][0]['description']['identifier']
            result[cls_name] = geo_id
            converted += 1
            status_msg = f"[{method_used}] Converted {cls_name} to {model_stem}.geo.json ({geo_id})"
            if conversion_warnings:
                status_msg += f"  ({len(conversion_warnings)} warnings)"
            print(status_msg)
            if conversion_warnings:
                for warning in conversion_warnings[:3]:
                    print(f"       {warning}")
        except Exception as e:
            print(f"Failed to write {out_path}: {e}")
    if converted:
        print(f"[model-convert] Converted {converted} Java model class(es) to GeckoLib geometry")
    return result
_LAYERDEF_GEO_MAP: Dict[str, str] = {}
def normalise_all_geometry_to_geckolib(resource_pack: str, namespace: str) -> int:
    geom_dir = os.path.join(resource_pack, "geometry")
    os.makedirs(geom_dir, exist_ok=True)
    written = 0
    seen_stems: set = set()
    sweep_dirs = [
        os.path.join(resource_pack, "geometry"),
        os.path.join(resource_pack, "models"),
    ]
    for sweep_dir in sweep_dirs:
        if not os.path.isdir(sweep_dir):
            continue
        for dirpath, _dirs, files in os.walk(sweep_dir):
            for fname in files:
                lower = fname.lower()
                if not lower.endswith(".json") and not lower.endswith(".geo.json"):
                    continue
                src = os.path.join(dirpath, fname)
                try:
                    with open(src, "r", encoding="utf-8", errors="ignore") as fh:
                        data = json.load(fh)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                if "minecraft:geometry" in data:
                    base = re.sub(r'\.geo(\.json)?$', '', fname, flags=re.I)
                    base = re.sub(r'\.json$', '', base, flags=re.I)
                    stem = sanitize_identifier(base) or sanitize_identifier(fname)
                    dest_name = stem + ".geo.json"
                    dest = os.path.join(geom_dir, dest_name)
                    if os.path.abspath(src) != os.path.abspath(dest) and stem not in seen_stems:
                        geos = data.get("minecraft:geometry", [])
                        if isinstance(geos, list):
                            for g in geos:
                                desc = g.get("description") or {}
                                ident = desc.get("identifier", "")
                                if ident and not ident.startswith(f"geometry.{namespace}"):
                                    pass
                        safe_write_json(dest, data)
                        seen_stems.add(stem)
                        written += 1
                        print(f"GeckoLib to rp/geometry/{dest_name}")
                    else:
                        seen_stems.add(stem)
                    continue
                if "elements" in data or "groups" in data:
                    base = re.sub(r'\.json$', '', fname, flags=re.I)
                    stem = sanitize_identifier(base) or sanitize_identifier(fname)
                    dest_name = stem + ".geo.json"
                    dest = os.path.join(geom_dir, dest_name)
                    if stem in seen_stems or os.path.exists(dest):
                        seen_stems.add(stem)
                        continue
                    try:
                        converted = convert_vanilla_model_to_geckolib(data, stem)
                        geos = converted.get("minecraft:geometry", [])
                        if geos:
                            desc = geos[0].setdefault("description", {})
                            current_id = desc.get("identifier", "")
                            if not current_id or current_id == f"geometry.{stem}":
                                desc["identifier"] = f"geometry.{namespace}.{stem}"
                        safe_write_json(dest, converted)
                        seen_stems.add(stem)
                        written += 1
                        print(f"Vanilla to GeckoLib to rp/geometry/{dest_name}")
                    except Exception as e:
                        print(f"[geo-sweep] Conversion failed for {src}: {e}")
                    continue
    if written:
        print(f"Normalized {written} model file(s) to rp/geometry/")
    return written
def copy_geckolib_animations_from_jar(jar_path: str, resource_pack: str):
    with zipfile.ZipFile(jar_path, 'r') as jar:
        for file in jar.namelist():
            lower = file.lower()
            if ("animation" in lower and lower.endswith(".json")) or ("/animations/" in lower and lower.endswith(".json")):
                dest_name = sanitize_filename_keep_ext(os.path.basename(file))
                dest = os.path.join(resource_pack, "animations", dest_name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with jar.open(file) as src_file, open(dest, "wb") as out_file:
                    shutil.copyfileobj(src_file, out_file)
                print(f"Copied animation file from JAR: {file} -> {dest}")
def rp_texture_exists(texture_path_without_ext: str) -> bool:
    variants = [
        os.path.join(RP_FOLDER, "textures", texture_path_without_ext + ".png"),
        os.path.join(RP_FOLDER, "textures", texture_path_without_ext, os.path.basename(texture_path_without_ext) + ".png"),
        os.path.join(RP_FOLDER, "textures", os.path.basename(texture_path_without_ext) + ".png")
    ]
    for p in variants:
        if os.path.exists(p):
            return True
    return False
def resolve_texture_reference(namespace: str, texture_hint: Optional[str], kind_hint: str, fallback_name: Optional[str] = None) -> str:
    ns = sanitize_identifier(namespace) or "converted"
    if texture_hint:
        candidate = texture_hint.split(":")[-1]
        candidate = candidate.replace(".png", "").strip("/")
        if candidate.startswith("textures/"):
            candidate = candidate[len("textures/"):]
        for probe in [
            candidate,
            f"{kind_hint}/{candidate}",
            f"{kind_hint}/{os.path.basename(candidate)}",
        ]:
            if rp_texture_exists(probe):
                return f"{ns}:{probe}"
        return f"{ns}:{candidate if '/' in candidate else kind_hint + '/' + sanitize_identifier(candidate)}"
    if fallback_name:
        for probe in [f"{kind_hint}/{fallback_name}", fallback_name]:
            if rp_texture_exists(probe):
                return f"{ns}:{probe}"
        return f"{ns}:{kind_hint}/{sanitize_identifier(fallback_name)}"
    return f"{ns}:{kind_hint}/missing_texture"
def texture_ref_to_rp_path(texture_ref: Optional[str], default_kind: str = "entity") -> str:
    if not texture_ref:
        return f"{default_kind}/missing_texture"
    path = texture_ref.split(":", 1)[-1]
    if path.startswith("textures/"):
        path = path[len("textures/"):]
    return path
def generate_texture_registry(pack_name: str):
    item_textures: Dict[str, Dict[str, str]] = {}
    block_textures: Dict[str, Dict[str, str]] = {}
    items_dir = os.path.join(RP_FOLDER, "textures", "items")
    blocks_dir = os.path.join(RP_FOLDER, "textures", "blocks")
    if os.path.isdir(items_dir):
        for root, _, files in os.walk(items_dir):
            for file in files:
                if file.lower().endswith(".png"):
                    rel_dir = os.path.relpath(root, os.path.join(RP_FOLDER, "textures", "items"))
                    name = os.path.splitext(file)[0]
                    if rel_dir != ".":
                        key = os.path.join(rel_dir, name).replace("\\", "/")
                    else:
                        key = name
                    item_textures[key] = {"textures": f"textures/items/{key}"}
    if os.path.isdir(blocks_dir):
        for root, _, files in os.walk(blocks_dir):
            for file in files:
                if file.lower().endswith(".png"):
                    rel_dir = os.path.relpath(root, os.path.join(RP_FOLDER, "textures", "blocks"))
                    name = os.path.splitext(file)[0]
                    if rel_dir != ".":
                        key = os.path.join(rel_dir, name).replace("\\", "/")
                    else:
                        key = name
                    block_textures[key] = {"textures": f"textures/blocks/{key}"}
    item_registry = {
        "resource_pack_name": pack_name,
        "texture_name": "atlas.items",
        "texture_data": item_textures
    }
    item_path = os.path.join(RP_FOLDER, "textures", "item_texture.json")
    safe_write_json(item_path, item_registry)
    terrain_registry = {
        "resource_pack_name": pack_name,
        "texture_name": "atlas.terrain",
        "texture_data": block_textures
    }
    terrain_path = os.path.join(RP_FOLDER, "textures", "terrain_texture.json")
    safe_write_json(terrain_path, terrain_registry)
    print("Generated texture atlases (item_texture.json and terrain_texture.json).")
def normalize_geometry_file_identifiers():
    geom_dir = os.path.join(RP_FOLDER, "geometry")
    if not os.path.isdir(geom_dir):
        return
    for fname in os.listdir(geom_dir):
        if not (fname.lower().endswith(".geo.json") or fname.lower().endswith(".geo")):
            continue
        path = os.path.join(geom_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            try:
                txt = open(path, "r", encoding="utf-8", errors="ignore").read()
                m = re.search(r'"identifier"\s*:\s*["\']([^"\']+)["\']', txt)
                if not m:
                    continue
                orig = m.group(1)
                if orig.startswith("geometry."):
                    tail = orig.split(".", 1)[1]
                    newidf = "geometry." + sanitize_identifier(tail)
                else:
                    newidf = "geometry." + sanitize_identifier(orig)
                txt2 = txt.replace(m.group(0), f'"identifier": "{newidf}"')
                with open(path, "w", encoding="utf-8") as fh2:
                    fh2.write(txt2)
                print(f"[geom-normalize] Rewrote identifier in {path}: {orig} -> {newidf}")
            except Exception:
                continue
            continue
        def set_identifiers(obj):
            changed = False
            if isinstance(obj, dict):
                for k, v in list(obj.items()):
                    if k == "identifier" and isinstance(v, str):
                        orig = v
                        if orig.startswith("geometry."):
                            tail = orig.split(".", 1)[1]
                            newidf = "geometry." + sanitize_identifier(tail)
                        else:
                            newidf = "geometry." + sanitize_identifier(orig)
                        obj[k] = newidf
                        changed = True
                    else:
                        ch = set_identifiers(v)
                        changed = changed or ch
            elif isinstance(obj, list):
                for item in obj:
                    ch = set_identifiers(item)
                    changed = changed or ch
            return changed
        changed = set_identifiers(data)
        if changed:
            safe_write_json(path, data)
            print(f"[geom-normalize] Normalized identifiers in {path}")
def fix_animation_format_versions():
    for folder in [os.path.join(RP_FOLDER, "animations"), os.path.join(BP_FOLDER, "animations")]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(folder, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("format_version") == "1.8.0":
                    data["format_version"] = "1.10.0"
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    print(f"[anim] Fixed format_version 1.8.0->1.10.0 in {fname}")
            except Exception:
                pass
def sanitize_animation_keys_in_files():
    anim_dir = os.path.join(RP_FOLDER, "animations")
    if not os.path.isdir(anim_dir):
        return
    for fname in os.listdir(anim_dir):
        if not fname.lower().endswith(".json"):
            continue
        path = os.path.join(anim_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        anims = data.get("animations")
        if not isinstance(anims, dict):
            continue
        new_anims = {}
        changed = False
        for k, v in anims.items():
            new_key = canonicalize_animation_id(k)
            if not new_key:
                new_key = k
            if new_key != k or new_key in new_anims:
                changed = True
            if new_key in new_anims:
                continue
            new_anims[new_key] = v
        if changed:
            data["animations"] = new_anims
            safe_write_json(path, data)
            print(f"[anim-normalize] Normalized animation keys in {path}")
def canonicalize_animation_id(raw: str, namespace: Optional[str] = None, entity_name: Optional[str] = None) -> str:
    MOTION_KEYWORDS = {
        "idle", "stand", "pose", "float",
        "walk", "walking",
        "run", "running", "chase", "sprint",
        "attack", "strike", "bite", "swipe", "slam", "lunge", "claw",
        "hurt", "hit", "flinch", "pain",
        "death", "die", "dying", "dead",
        "sit", "sitting", "crouch", "lay",
        "swim", "swimming",
        "fly", "flying", "hover", "glide",
        "sleep", "sleeping", "rest",
        "spawn", "appear", "emerge", "summon",
        "open", "close", "blink", "tail", "wing", "flap",
    }
    if raw is None:
        return ""
    s = str(raw).strip().strip('"')
    s = s.strip("'")
    if not s:
        return ""
    s = s.replace("\\", "/")
    s = re.sub(r'\.json$', '', s, flags=re.I)
    if s.lower().startswith("animations/"):
        s = s.split("/", 1)[1]
    s = s.replace("/", ".")
    ns = sanitize_identifier(namespace) if namespace else ""
    ent = sanitize_identifier(entity_name) if entity_name else ""
    if s.startswith("animation."):
        tail = s[len("animation."):]
        parts = [sanitize_identifier(p) for p in tail.split(".")]
        parts = [p for p in parts if p]
        if not parts:
            return ""
        last = parts[-1].lower()
        if not any(kw in last for kw in MOTION_KEYWORDS):
            return ""
        return "animation." + ".".join(parts)
    bare = sanitize_identifier(s)
    if not bare:
        return ""
    if not any(kw in bare.lower() for kw in MOTION_KEYWORDS):
        return ""
    if ns and ent:
        if bare.startswith(f"{ns}.{ent}."):
            return f"animation.{bare}"
        if bare.startswith(f"{ent}."):
            return f"animation.{ns}.{bare}"
        return f"animation.{ns}.{ent}.{bare}"
    if ns:
        if bare.startswith(f"{ns}."):
            return f"animation.{bare}"
        return f"animation.{ns}.{bare}"
    return f"animation.{bare}"
def build_rp_asset_index():
    global _RP_ASSET_INDEX
    textures: list = []
    geometry: list = []
    tex_root = os.path.join(RP_FOLDER, "textures")
    if os.path.isdir(tex_root):
        for dirpath, _, filenames in os.walk(tex_root):
            for fname in filenames:
                if fname.lower().endswith(".png"):
                    abs_path = os.path.join(dirpath, fname)
                    rel = os.path.relpath(abs_path, tex_root).replace("\\", "/")
                    rel_no_ext = os.path.splitext(rel)[0]
                    textures.append((rel_no_ext, abs_path))
    for geo_root in [os.path.join(RP_FOLDER, "models"), os.path.join(RP_FOLDER, "geometry")]:
        if not os.path.isdir(geo_root):
            continue
        for dirpath, _, filenames in os.walk(geo_root):
            for fname in filenames:
                if not (fname.lower().endswith(".geo.json") or fname.lower().endswith(".json")):
                    continue
                abs_path = os.path.join(dirpath, fname)
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as fh:
                        data = json.load(fh)
                    geos = data.get("minecraft:geometry", [])
                    extracted = False
                    if isinstance(geos, list):
                        for g in geos:
                            ident = (g.get("description") or {}).get("identifier", "")
                            if ident:
                                geometry.append((ident, abs_path))
                                extracted = True
                    if not extracted:
                        stem = re.sub(r'\.geo(\.json)?$', '', fname, flags=re.I)
                        geometry.append((f"geometry.{sanitize_identifier(stem)}", abs_path))
                except Exception:
                    stem = re.sub(r'\.geo(\.json)?$', '', fname, flags=re.I)
                    geometry.append((f"geometry.{sanitize_identifier(stem)}", abs_path))
    _RP_ASSET_INDEX["textures"] = textures
    _RP_ASSET_INDEX["geometry"] = geometry

    if _RP_ASSET_INDEX["flipbook_textures"]:
        flipbook_path = os.path.join(RP_FOLDER, "textures", "flipbook_textures.json")
        os.makedirs(os.path.dirname(flipbook_path), exist_ok=True)
        with open(flipbook_path, "w", encoding="utf-8") as f:
            json.dump(_RP_ASSET_INDEX["flipbook_textures"], f, indent=2)
        print(f"[flipbook] Wrote flipbook_textures.json with {len(_RP_ASSET_INDEX['flipbook_textures'])} animated texture(s)")
    print(f"[index] Indexed {len(textures)} texture(s) and {len(geometry)} geometry model(s)")
def _camel_tokens(s: str) -> set:
    s = re.sub(r'([A-Z])', r'_\1', s).lower().strip("_")
    return {t for t in re.split(r'[_\s\-]+', s) if len(t) > 1}
_ASSET_NOISE = frozenset({
    "entity", "mob", "model", "geo", "texture", "renderer", "render",
    "layer", "type", "base", "abstract", "common", "generic",
})
def _asset_score(entity_tokens: set, candidate_stem: str) -> float:
    cand_base = os.path.basename(candidate_stem)
    cand_tokens = _camel_tokens(cand_base) | set(cand_base.split("_"))
    cand_tokens = {t for t in cand_tokens if len(t) > 1}
    if not entity_tokens or not cand_tokens:
        return 0.0
    et = entity_tokens - _ASSET_NOISE or entity_tokens
    ct = cand_tokens - _ASSET_NOISE or cand_tokens
    shared = et & ct
    if not shared:
        ent_str = "".join(sorted(et))
        cand_str = "".join(sorted(ct))
        if ent_str in cand_str or cand_str in ent_str:
            return 0.38
        for e in sorted(et, key=len, reverse=True):
            if len(e) >= 4:
                for c in ct:
                    if e in c or c in e:
                        return 0.32
        return 0.0
    precision = len(shared) / len(ct) if ct else 0.0
    recall    = len(shared) / len(et) if et else 0.0
    if precision + recall == 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)
def load_geometry_identifiers() -> Tuple[Dict[str, str], Dict[Tuple[Optional[str], Optional[str]], str]]:
    map_by_file = {}
    map_by_ns_name = {}
    geom_dir = os.path.join(RP_FOLDER, "geometry")
    if not os.path.isdir(geom_dir):
        return map_by_file, map_by_ns_name
    for fname in os.listdir(geom_dir):
        if not (fname.lower().endswith(".geo.json") or fname.lower().endswith(".geo")):
            continue
        path = os.path.join(geom_dir, fname)
        identifier = None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            try:
                txt = open(path, "r", encoding="utf-8", errors="ignore").read()
                m = re.search(r'"identifier"\s*:\s*["\']([^"\']+)["\']', txt)
                identifier = m.group(1) if m else None
            except Exception:
                identifier = None
        else:
            def find_identifier(obj):
                if isinstance(obj, dict):
                    if "identifier" in obj and isinstance(obj["identifier"], str):
                        return obj["identifier"]
                    for v in obj.values():
                        res = find_identifier(v)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = find_identifier(item)
                        if res:
                            return res
                return None
            identifier = find_identifier(data)
        basename = os.path.splitext(os.path.splitext(fname)[0])[0]
        basename_norm = sanitize_identifier(basename) or basename.lower()
        if identifier:
            map_by_file[basename_norm] = identifier
            parts = identifier.split(".")
            if len(parts) >= 3 and parts[0] == "geometry":
                ns = parts[1]
                name = ".".join(parts[2:])
                map_by_ns_name[(sanitize_identifier(ns), sanitize_identifier(name))] = identifier
                map_by_ns_name[(None, sanitize_identifier(name))] = identifier
            elif len(parts) >= 2 and parts[0] == "geometry":
                name = ".".join(parts[1:])
                map_by_ns_name[(None, sanitize_identifier(name))] = identifier
        else:
            map_by_file[basename_norm] = build_geometry_id(None, basename_norm)
    return map_by_file, map_by_ns_name
def load_animation_keys() -> Dict[str, Set[str]]:
    anim_dir = os.path.join(RP_FOLDER, "animations")
    result: Dict[str, Set[str]] = {}
    if not os.path.isdir(anim_dir):
        return result
    for fname in os.listdir(anim_dir):
        if not fname.lower().endswith(".json"):
            continue
        path = os.path.join(anim_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        keys: Set[str] = set()
        if isinstance(data, dict):
            anims = data.get("animations") or {}
            if isinstance(anims, dict):
                for k in anims.keys():
                    keys.add(k)
        result[os.path.splitext(fname)[0].lower()] = keys
    return result
def read_all_java_files(root_dir=".") -> Dict[str, str]:
    java_files = {}
    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.endswith(".java"):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        java_files[path] = fh.read()
                except Exception:
                    continue
    return java_files
def extract_class_name(java_code: str) -> Optional[str]:
    ast = JavaAST(java_code)
    name = ast.primary_class_name()
    if name:
        return name
    m = re.search(r'\b(public\s+)?(class|interface|enum)\s+([A-Z][A-Za-z0-9_]*)', java_code)
    if m:
        return m.group(3)
    return None
def find_model_geometry_in_code(java_code: str) -> Optional[Tuple[Optional[str], str]]:
    ast = JavaAST(java_code)
    ast._parse()
    if ast._tree is not None:
        for node in ast.object_creations_of('ResourceLocation'):
            args = getattr(node, 'arguments', []) or []
            ns_val, path_val = None, None
            if len(args) >= 2:
                if isinstance(args[0], javalang.tree.Literal):
                    ns_val = args[0].value.strip('"').strip("'")
                if isinstance(args[1], javalang.tree.Literal):
                    path_val = args[1].value.strip('"').strip("'")
            elif len(args) == 1:
                if isinstance(args[0], javalang.tree.Literal):
                    raw = args[0].value.strip('"').strip("'")
                    if ':' in raw:
                        ns_val, path_val = raw.split(':', 1)
                    else:
                        path_val = raw
            if path_val and ('geo/' in path_val or path_val.endswith('.geo.json') or path_val.endswith('.geo')):
                base = os.path.basename(path_val)
                name = re.sub(r'\.geo(\.json)?$', '', base, flags=re.IGNORECASE)
                return (ns_val.lower() if ns_val else None, sanitize_identifier(name))
        for lit in ast.all_string_literals():
            if 'geo/' in lit or lit.endswith('.geo.json') or lit.endswith('.geo'):
                ns, path = (lit.split(':', 1) if ':' in lit else (None, lit))
                base = os.path.basename(path)
                name = re.sub(r'\.geo(\.json)?$', '', base, flags=re.IGNORECASE)
                return (ns.lower() if ns else None, sanitize_identifier(name))
    m = re.search(r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_\-]+)["\']\s*,\s*["\']([^"\']*?geo/[^"\']*?\.geo(?:\.json)?)["\']\s*\)', java_code, re.IGNORECASE)
    if m:
        ns = m.group(1).lower()
        base = os.path.basename(m.group(2))
        name = re.sub(r'\.geo(\.json)?$', '', base, flags=re.IGNORECASE)
        return (ns, sanitize_identifier(name))
    m2 = re.search(r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_\-]+:[^"\']*?geo/[^"\']*?\.geo(?:\.json)?)["\']\s*\)', java_code, re.IGNORECASE)
    if m2:
        raw = m2.group(1)
        ns, path = (raw.split(':', 1) if ':' in raw else (None, raw))
        name = re.sub(r'\.geo(\.json)?$', '', os.path.basename(path), flags=re.IGNORECASE)
        return (ns.lower() if ns else None, sanitize_identifier(name))
    m3 = re.search(r'["\']([a-z0-9_\-:\/]*?geo\/[a-z0-9_\-]+(?:\.geo(?:\.json)?)?)["\']', java_code, re.IGNORECASE)
    if m3:
        raw = m3.group(1)
        ns, path = (raw.split(':', 1) if ':' in raw else (None, raw))
        name = re.sub(r'\.geo(\.json)?$', '', os.path.basename(path), flags=re.IGNORECASE)
        return (ns.lower() if ns else None, sanitize_identifier(name))
    m5 = re.search(r'["\']([a-z0-9_\-:\/]+\.geo(?:\.json)?)["\']', java_code, re.IGNORECASE)
    if m5:
        raw = m5.group(1)
        ns, path = (raw.split(':', 1) if ':' in raw else (None, raw))
        name = re.sub(r'\.geo(\.json)?$', '', os.path.basename(path), flags=re.IGNORECASE)
        return (ns.lower() if ns else None, sanitize_identifier(name))
    return None
_RENDERER_MAP: Dict[str, Dict] = {}
def build_renderer_entity_map():
    global _RENDERER_MAP
    _RENDERER_MAP = {}
    renderer_to_entity: Dict[str, str] = {}
    model_to_entity: Dict[str, str] = {}
    entity_to_renderer: Dict[str, str] = {}
    cls_to_code: Dict[str, str] = {}
    cls_to_path: Dict[str, str] = {}
    for path, code in _ALL_JAVA_FILES.items():
        cls = extract_class_name(code)
        if not cls:
            continue
        cls_to_code[cls] = code
        cls_to_path[cls] = path
        m = re.search(
            r'\bclass\s+(\w+)\s+extends\s+\w*(?:Renderer|Render)\w*\s*<\s*(\w+)',
            code
        )
        if m:
            renderer_cls, entity_arg = m.group(1), m.group(2)
            renderer_to_entity[renderer_cls] = entity_arg
        m2 = re.search(
            r'\bclass\s+(\w+)\s+extends\s+\w*(?:Model|GeoModel)\w*\s*<\s*(\w+)',
            code
        )
        if m2:
            model_cls, entity_arg = m2.group(1), m2.group(2)
            model_to_entity[model_cls] = entity_arg
        for m3 in re.finditer(
            r'EntityRenderers\s*\.\s*register\s*\(\s*(\w+(?:\.\w+)*)\s*,\s*(\w+)\s*::',
            code
        ):
            etype_expr, renderer_cls = m3.group(1), m3.group(2)
            etype_simple = etype_expr.split(".")[-1]
            entity_to_renderer[etype_simple] = renderer_cls
            entity_to_renderer[etype_simple.lower()] = renderer_cls
        for m4 in re.finditer(
            r'registerEntityRenderingHandler\s*\(\s*(\w+(?:\.\w+)*)\s*,\s*\w+\s*->\s*new\s+(\w+)',
            code
        ):
            etype_expr, renderer_cls = m4.group(1), m4.group(2)
            etype_simple = etype_expr.split(".")[-1]
            entity_to_renderer[etype_simple] = renderer_cls
            entity_to_renderer[etype_simple.lower()] = renderer_cls
        for m5 in re.finditer(
            r'bindEntityRenderer\s*\(\s*(\w+)\.class\s*,\s*(\w+)\.class',
            code
        ):
            entity_to_renderer[m5.group(1)] = m5.group(2)
    renderer_to_model: Dict[str, str] = {}
    for renderer_cls, rcode in {c: cls_to_code[c] for c in renderer_to_entity if c in cls_to_code}.items():
        m = re.search(r'super\s*\([^)]*new\s+(\w+)', rcode)
        if m:
            renderer_to_model[renderer_cls] = m.group(1)
        m2 = re.search(r'this\.model\s*=\s*new\s+(\w+)', rcode)
        if m2:
            renderer_to_model[renderer_cls] = m2.group(1)
    def _put(entity_cls: str, renderer_cls: Optional[str], model_cls: Optional[str]):
        if not entity_cls:
            return
        entry = _RENDERER_MAP.setdefault(entity_cls, {})
        if renderer_cls and "renderer" not in entry:
            entry["renderer"] = renderer_cls
            entry["renderer_code"] = cls_to_code.get(renderer_cls, "")
        if model_cls and "model" not in entry:
            entry["model"] = model_cls
            entry["model_code"] = cls_to_code.get(model_cls, "")
    for renderer_cls, entity_cls in renderer_to_entity.items():
        model_cls = renderer_to_model.get(renderer_cls)
        _put(entity_cls, renderer_cls, model_cls)
        _put(renderer_cls, renderer_cls, model_cls)
    for model_cls, entity_cls in model_to_entity.items():
        _put(entity_cls, None, model_cls)
    for etype_key, renderer_cls in entity_to_renderer.items():
        camel = "".join(w.capitalize() for w in etype_key.lower().split("_"))
        model_cls = renderer_to_model.get(renderer_cls)
        _put(camel,    renderer_cls, model_cls)
        _put(etype_key, renderer_cls, model_cls)
    found = sum(1 for v in _RENDERER_MAP.values() if v.get("renderer") or v.get("model"))
    print(f"[renderer-map] Mapped {found} entity→renderer/model relationship(s) from {len(_ALL_JAVA_FILES)} source files")
def build_geckolib_mappings(java_root="."):
    java_files = read_all_java_files(java_root)
    class_to_path: Dict[str, str] = {}
    class_code_map: Dict[str, str] = {}
    for path, code in java_files.items():
        cls = extract_class_name(code)
        if cls:
            class_to_path[cls] = path
            class_code_map[cls] = code
    model_map: Dict[str, Tuple[Optional[str], str]] = {}
    renderer_model: Dict[str, str] = {}
    renderer_entity: Dict[str, str] = {}
    for path, code in class_code_map.items():
        geom = find_model_geometry_in_code(code)
        if geom:
            model_map[path] = geom
    for cls, code in class_code_map.items():
        ast = JavaAST(code)
        ast._parse()
        if ast._tree is not None:
            for cls_decl in ast.get_class_declarations():
                if cls_decl.extends and hasattr(cls_decl.extends, 'name'):
                    if cls_decl.extends.name == 'GeoEntityRenderer':
                        args = getattr(cls_decl.extends, 'arguments', None) or []
                        if args:
                            arg = args[0]
                            ent = JavaAST.strip_generics(
                                arg.type.name if hasattr(arg, 'type') and hasattr(arg.type, 'name')
                                else (arg.name if hasattr(arg, 'name') else '')
                            )
                            if ent:
                                renderer_entity[cls] = ent
            for ctype in ast.all_object_creation_types():
                if ctype in class_code_map and ('Model' in ctype or ctype in model_map):
                    renderer_model[cls] = ctype
                    break
        else:
            m = re.search(r'extends\s+GeoEntityRenderer\s*<\s*([A-Za-z0-9_<>.,\s]+)\s*>', code)
            if m:
                ent = re.sub(r'<.*?>', '', m.group(1).split(",")[0]).strip()
                if ent:
                    renderer_entity[cls] = ent
            model_candidates = set(re.findall(r'new\s+([A-Z][A-Za-z0-9_]*)\s*\(', code))
            for cand in model_candidates:
                if cand in class_code_map and ('Model' in cand or cand in model_map):
                    renderer_model[cls] = cand
                    break
        if cls not in renderer_model:
            m2 = re.search(r'([A-Z][A-Za-z0-9_]*Model)\s+[a-zA-Z0-9_]+\s*=\s*new\s+([A-Z][A-Za-z0-9_]*Model)\s*\(', code)
            if m2:
                renderer_model[cls] = m2.group(1)
    entity_to_geometry: Dict[str, Tuple[Optional[str], str]] = {}
    entity_to_model: Dict[str, str] = {}
    for renderer_cls, model_cls in renderer_model.items():
        geom = model_map.get(model_cls)
        ent = renderer_entity.get(renderer_cls)
        if ent and geom:
            entity_to_geometry[ent] = geom
            entity_to_model[ent] = model_cls
    for renderer_cls, code in class_code_map.items():
        if renderer_cls not in renderer_model:
            ast = JavaAST(code)
            ast._parse()
            found_model = None
            if ast._tree is not None:
                for ctype in ast.all_object_creation_types():
                    if ctype in model_map:
                        found_model = ctype
                        break
            else:
                m = re.search(r'super\s*\(\s*[^\)]*new\s+([A-Z][A-Za-z0-9_]*)\s*\(', code)
                if m:
                    found_model = m.group(1)
            if found_model and found_model in model_map:
                renderer_model[renderer_cls] = found_model
        if renderer_cls in renderer_model and renderer_cls not in renderer_entity:
            ast2 = JavaAST(code)
            ast2._parse()
            if ast2._tree is not None:
                for cls_decl in ast2.get_class_declarations():
                    if cls_decl.extends and cls_decl.extends.name == 'GeoEntityRenderer':
                        args = getattr(cls_decl.extends, 'arguments', None) or []
                        if args:
                            arg = args[0]
                            ent = JavaAST.strip_generics(
                                arg.type.name if hasattr(arg, 'type') and hasattr(arg.type, 'name')
                                else (arg.name if hasattr(arg, 'name') else '')
                            )
                            if ent:
                                renderer_entity[renderer_cls] = ent
            else:
                m2 = re.search(r'extends\s+GeoEntityRenderer\s*<\s*([A-Za-z0-9_<>.,\s]+)\s*>', code)
                if m2:
                    ent = re.sub(r'<.*?>', '', m2.group(1).split(",")[0]).strip()
                    if ent:
                        renderer_entity[renderer_cls] = ent
    for renderer_cls, model_cls in renderer_model.items():
        ent = renderer_entity.get(renderer_cls)
        geom = model_map.get(model_cls)
        if ent and geom:
            entity_to_geometry[ent] = geom
            entity_to_model[ent] = model_cls
    global _LAYERDEF_GEO_MAP
    if _LAYERDEF_GEO_MAP:
        for renderer_cls, model_cls in renderer_model.items():
            if model_cls in _LAYERDEF_GEO_MAP:
                ent = renderer_entity.get(renderer_cls)
                if ent and ent not in entity_to_geometry:
                    geo_id = _LAYERDEF_GEO_MAP[model_cls]
                    parts = geo_id.split('.')
                    ns_h  = parts[1] if len(parts) >= 3 else None
                    nm_h  = '.'.join(parts[2:]) if len(parts) >= 3 else geo_id
                    entity_to_geometry[ent] = (ns_h, nm_h)
                    entity_to_model[ent]    = model_cls
        for model_cls, geo_id in _LAYERDEF_GEO_MAP.items():
            for ent_cls in renderer_entity.values():
                if ent_cls not in entity_to_geometry:
                    mc_stem = re.sub(r'(?i)Model$', '', model_cls).lower()
                    en_stem = re.sub(r'(?i)Entity$', '', ent_cls).lower()
                    if mc_stem and en_stem and mc_stem == en_stem:
                        parts = geo_id.split('.')
                        ns_h  = parts[1] if len(parts) >= 3 else None
                        nm_h  = '.'.join(parts[2:]) if len(parts) >= 3 else geo_id
                        entity_to_geometry[ent_cls] = (ns_h, nm_h)
    return {
        "class_code_map": class_code_map,
        "class_to_path": class_to_path,
        "model_map": model_map,
        "renderer_model": renderer_model,
        "renderer_entity": renderer_entity,
        "entity_to_geometry": entity_to_geometry,
        "entity_to_model": entity_to_model
    }
_JAVA_ATTR_NAME_MAP: Dict[str, str] = {
    "MAX_HEALTH": "health",
    "GENERIC_MAX_HEALTH": "health",
    "maxHealth": "health",
    "HEALTH": "health",
    "MOVEMENT_SPEED": "movement_speed",
    "GENERIC_MOVEMENT_SPEED": "movement_speed",
    "movementSpeed": "movement_speed",
    "FLYING_SPEED": "movement_speed",
    "SWIM_SPEED": "movement_speed",
    "ATTACK_DAMAGE": "attack_damage",
    "GENERIC_ATTACK_DAMAGE": "attack_damage",
    "attackDamage": "attack_damage",
    "ATTACK_SPEED": "attack_speed",
    "GENERIC_ATTACK_SPEED": "attack_speed",
    "ATTACK_KNOCKBACK": "attack_knockback",
    "GENERIC_ATTACK_KNOCKBACK": "attack_knockback",
    "FOLLOW_RANGE": "follow_range",
    "GENERIC_FOLLOW_RANGE": "follow_range",
    "followRange": "follow_range",
    "ARMOR": "armor",
    "GENERIC_ARMOR": "armor",
    "ARMOR_TOUGHNESS": "armor_toughness",
    "GENERIC_ARMOR_TOUGHNESS": "armor_toughness",
    "KNOCKBACK_RESISTANCE": "knockback_resistance",
    "GENERIC_KNOCKBACK_RESISTANCE": "knockback_resistance",
    "knockbackResistance": "knockback_resistance",
    "LUCK": "luck",
    "GENERIC_LUCK": "luck",
    "HORSE_JUMP_STRENGTH": "jump_strength",
    "ZOMBIE_SPAWN_REINFORCEMENTS": "spawn_reinforcements",
    "SPAWN_REINFORCEMENTS_CHANCE": "spawn_reinforcements",
}
_SRG_ATTR_FIELD_MAP: Dict[str, str] = {
    "f_22279_": "movement_speed",
    "f_22276_": "follow_range",
    "f_22284_": "health",
    "f_22281_": "knockback_resistance",
    "f_22277_": "armor",
    "f_22278_": "attack_damage",
    "m_6113_": "health",
    "m_6114_": "follow_range",
    "m_6115_": "movement_speed",
    "m_6116_": "attack_damage",
}
def _parse_java_float(s: str) -> Optional[float]:
    if s is None:
        return None
    cleaned = re.sub(r'[DdFfLl]$', '', str(s).strip())
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None
def _extract_attr_block(java_code: str) -> str:
    method_patterns = [
        r'(?:public\s+static\s+)?(?:AttributeSupplier|AttributeModifierMap|AttributeMap|Builder)\s*'
        r'[\w.]*\s*createAttributes\s*\(\s*\)\s*\{',
        r'(?:public\s+static\s+)?(?:AttributeSupplier|AttributeModifierMap|AttributeMap|Builder)\s*'
        r'[\w.]*\s*getDefaultAttributes\s*\(\s*\)\s*\{',
        r'(?:public\s+static\s+)?(?:AttributeSupplier|AttributeModifierMap|Builder)\s*'
        r'[\w.]*\s*createMobAttributes\s*\(\s*\)\s*\{',
        r'(?:public\s+static\s+)?(?:AttributeSupplier|AttributeModifierMap|Builder)\s*'
        r'[\w.]*\s*createMonsterAttributes\s*\(\s*\)\s*\{',
        r'(?:public\s+static\s+)?(?:AttributeSupplier|AttributeModifierMap|Builder)\s*'
        r'[\w.]*\s*createAnimalAttributes\s*\(\s*\)\s*\{',
        r'static\s+\w*Builder\w*\s+\w+Attributes\w*\s*\(\s*\)\s*\{',
    ]
    for pat in method_patterns:
        m = re.search(pat, java_code, re.IGNORECASE | re.DOTALL)
        if m:
            start = m.end() - 1
            depth = 0
            i = start
            while i < len(java_code):
                if java_code[i] == '{':
                    depth += 1
                elif java_code[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return java_code[start:i + 1]
                i += 1
    return java_code
def extract_attributes_from_java(java_code: str) -> dict:
    results: Dict[str, float] = {}
    block = _extract_attr_block(java_code)
    for m in re.finditer(
        r'\.add\s*\(\s*(?:[A-Za-z0-9_$]+\.)+([A-Z_][A-Z0-9_]*)\s*,\s*([-+]?[0-9]*\.?[0-9]+[DdFfLl]?)\s*\)',
        block, re.DOTALL
    ):
        bedrock_key = _JAVA_ATTR_NAME_MAP.get(m.group(1))
        val = _parse_java_float(m.group(2))
        if bedrock_key and val is not None and bedrock_key not in results:
            results[bedrock_key] = val
    for m in re.finditer(
        r'\.add\s*\(\s*["\']([A-Za-z_.]+)["\']\s*,\s*([-+]?[0-9]*\.?[0-9]+[DdFfLl]?)\s*\)',
        block, re.DOTALL
    ):
        raw_name = m.group(1).split(".")[-1].split(":")[-1]
        upper = re.sub(r'(?<=[a-z])(?=[A-Z])', '_', raw_name).upper()
        bedrock_key = _JAVA_ATTR_NAME_MAP.get(raw_name) or _JAVA_ATTR_NAME_MAP.get(upper)
        val = _parse_java_float(m.group(2))
        if bedrock_key and val is not None and bedrock_key not in results:
            results[bedrock_key] = val
    if not results:
        for m in re.finditer(
            r'\.add\s*\(\s*(f_[0-9_]+_)\s*,\s*([-+]?[0-9]*\.?[0-9]+[DdFfLl]?)\s*\)',
            block, re.DOTALL
        ):
            bedrock_key = _SRG_ATTR_FIELD_MAP.get(m.group(1))
            val = _parse_java_float(m.group(2))
            if bedrock_key and val is not None and bedrock_key not in results:
                results[bedrock_key] = val
    if not results:
        POSITIONAL_ORDER = [
            "movement_speed", "follow_range", "health",
            "knockback_resistance", "armor", "attack_damage"
        ]
        values = re.findall(r',\s*([-+]?[0-9]*\.?[0-9]+[DdFfLl]?)', block)
        for i, val_str in enumerate(values):
            if i < len(POSITIONAL_ORDER):
                val = _parse_java_float(val_str)
                if val is not None:
                    results[POSITIONAL_ORDER[i]] = val
    return results
def extract_animations_from_java(java_code: str, namespace: Optional[str] = None, entity_name: Optional[str] = None):
    animations = set()
    MOTION_KEYWORDS = {
        "idle", "stand", "standing", "pose", "float", "floating", "ambient",
        "breathe", "blink", "twitch", "fidget",
        "walk", "walking", "wander", "wander",
        "run", "running", "chase", "sprint", "sprinting", "dash", "gallop",
        "swim", "swimming", "paddle", "crawl", "slither", "jump", "jumping", "leap",
        "fly", "flying", "hover", "hovering", "glide", "gliding", "soar",
        "climb", "climbing", "roll",
        "attack", "attacking", "strike", "striking", "bite", "biting",
        "swipe", "swiping", "slam", "slamming", "lunge", "lunging",
        "claw", "clawing", "charge", "charging", "thrust", "shoot", "shooting",
        "breath", "roar",
        "hurt", "hit", "flinch", "pain", "stagger", "reel",
        "death", "die", "dying", "dead", "collapse", "fall",
        "sit", "sitting", "crouch", "crouching", "lay", "laying", "lie",
        "sleep", "sleeping", "rest", "resting", "curl",
        "spawn", "appear", "emerge", "summon", "summon",
        "open", "close", "dig", "eat", "drink",
        "tail", "wing", "wings", "ear", "head", "jaw", "mouth",
        "flap", "wag", "sway", "spin", "shake",
    }
    def _looks_like_anim_id(s: str) -> bool:
        if not s:
            return False
        if s.startswith("animation."):
            tail = s[len("animation."):]
            last_seg = tail.split(".")[-1].lower()
            return any(kw in last_seg for kw in MOTION_KEYWORDS)
        if "animations/" in s.lower():
            stem = re.sub(r'\.json$', '', s.split("/")[-1], flags=re.I).lower()
            return any(kw in stem for kw in MOTION_KEYWORDS)
        return False
    def _add(raw: str, trusted: bool = False):
        s = str(raw).strip().strip('"').strip("'")
        if not s or len(s) < 3:
            return
        if not trusted and not _looks_like_anim_id(s):
            return
        anim_id = canonicalize_animation_id(s, namespace, entity_name)
        if anim_id:
            animations.add(anim_id)
    ast = JavaAST(java_code)
    ast._parse()
    if ast._tree is not None:
        for inv in ast.invocations_of('addAnimation') + ast.invocations_of('then'):
            s = JavaAST.first_string_arg(inv)
            if s:
                _add(s, trusted=True)
        for method in ('thenPlay', 'thenLoop', 'thenPlayAndHold', 'playAnim', 'playAnimation', 'setAnimation'):
            for inv in ast.invocations_of(method):
                s = JavaAST.first_string_arg(inv)
                if s:
                    _add(s, trusted=True)
        for lit in ast.all_string_literals():
            _add(lit, trusted=False)
        for _, node in ast._tree.filter(javalang.tree.FieldDeclaration):
            for decl in node.declarators:
                if re.match(r'(?:ANIMATION|ANIM)[_A-Z0-9]*', decl.name, re.I):
                    if decl.initializer and isinstance(decl.initializer, javalang.tree.Literal):
                        val = decl.initializer.value.strip('"').strip("'")
                        _add(val, trusted=False)
    else:
        for m in re.finditer(r'addAnimation\(\s*["\']+([^"\']+)["\']+', java_code):
            _add(m.group(1), trusted=True)
        for m in re.finditer(r'animation\.([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)', java_code):
            _add("animation." + m.group(1), trusted=False)
        for m in re.finditer(r'\.then\s*\(\s*["\']+([^"\']+)["\']+', java_code):
            _add(m.group(1), trusted=True)
        for m in re.finditer(r'animations/([^"\'\.]+)\.json', java_code, re.I):
            _add(m.group(1), trusted=False)
        for m in re.finditer(r'(?:ANIMATION|ANIM)[_A-Z0-9]*\s*=\s*["\']+([^"\']+)["\']+', java_code):
            _add(m.group(1), trusted=False)
        for m in re.finditer(r'thenPlay\s*\(\s*["\'"]([^"\']+)["\'"]', java_code):
            _add(m.group(1), trusted=True)
        for m in re.finditer(r'thenLoop\s*\(\s*["\'"]([^"\']+)["\'"]', java_code):
            _add(m.group(1), trusted=True)
        for m in re.finditer(r'setAnimation\s*\(\s*RawAnimation\.begin\s*\(\s*\)\s*\.then(?:Play|Loop)\s*\(\s*["\'"]([^"\']+)["\'"]', java_code, re.DOTALL):
            _add(m.group(1), trusted=True)
        for m in re.finditer(r'playAnim(?:ation)?\s*\(\s*["\'"]([^"\']+)["\'"]', java_code):
            _add(m.group(1), trusted=True)
    return animations
VANILLA_GOALS: Set[str] = {
    "FloatGoal", "SwimGoal", "BreatheAirGoal",
    "NearestAttackableTargetGoal", "NearestAttackableTargetExpiringGoal",
    "ToggleableNearestAttackableTargetGoal", "NonTamedTargetGoal",
    "DefendVillageTargetGoal", "HurtByTargetGoal",
    "OwnerHurtByTargetGoal", "OwnerHurtTargetGoal", "ResetAngerGoal",
    "MeleeAttackGoal", "OcelotAttackGoal", "CreeperSwellGoal",
    "RangedAttackGoal", "RangedBowAttackGoal", "RangedCrossbowAttackGoal",
    "LeapAtTargetGoal", "MoveTowardsTargetGoal",
    "AvoidEntityGoal", "PanicGoal", "RunAroundLikeCrazyGoal",
    "FleeSunGoal", "RestrictSunGoal",
    "OpenDoorGoal", "InteractDoorGoal", "BreakDoorGoal",
    "BreakBlockGoal", "UseItemGoal",
    "FollowOwnerGoal", "FollowParentGoal", "FollowMobGoal",
    "FollowBoatGoal", "FollowSchoolLeaderGoal", "LlamaFollowCaravanGoal",
    "LandOnOwnersShoulderGoal", "MoveToBlockGoal",
    "MoveTowardsRestrictionGoal", "MoveThroughVillageGoal",
    "MoveThroughVillageAtNightGoal", "MoveTowardsRaidGoal",
    "ReturnToVillageGoal", "PatrolVillageGoal", "FindWaterGoal",
    "SitWhenOrderedToGoal", "SitGoal",
    "BreedGoal", "TemptGoal", "EatGrassGoal", "BegGoal",
    "TradeWithPlayerGoal", "LookAtCustomerGoal", "ShowVillagerFlowerGoal",
    "TriggerSkeletonTrapGoal", "DolphinJumpGoal", "JumpGoal",
    "CatLieOnBedGoal", "CatSitOnBlockGoal",
    "WaterAvoidingRandomStrollGoal", "RandomWalkingGoal",
    "RandomSwimmingGoal", "RandomStrollGoal",
    "LookAtGoal", "LookAtPlayerGoal", "LookAtWithoutMovingGoal",
    "LookRandomlyGoal", "RandomLookAroundGoal",
}
GOAL_NAME_ALIASES: Dict[str, str] = {
    "PathfinderGoalFloat":                    "FloatGoal",
    "PathfinderGoalSwimming":                 "SwimGoal",
    "PathfinderGoalMeleeAttack":              "MeleeAttackGoal",
    "PathfinderGoalBowShoot":                 "RangedBowAttackGoal",
    "PathfinderGoalArrowAttack":              "RangedAttackGoal",
    "PathfinderGoalCrossbowAttack":           "RangedCrossbowAttackGoal",
    "PathfinderGoalLeapAtTarget":             "LeapAtTargetGoal",
    "PathfinderGoalMoveTowardsTarget":        "MoveTowardsTargetGoal",
    "PathfinderGoalAvoidEntity":              "AvoidEntityGoal",
    "PathfinderGoalPanic":                    "PanicGoal",
    "PathfinderGoalOpenDoor":                 "OpenDoorGoal",
    "PathfinderGoalBreakDoor":                "BreakDoorGoal",
    "PathfinderGoalFollowOwner":              "FollowOwnerGoal",
    "PathfinderGoalFollowParent":             "FollowParentGoal",
    "PathfinderGoalFollowMob":                "FollowMobGoal",
    "PathfinderGoalMoveToBlock":              "MoveToBlockGoal",
    "PathfinderGoalRestrictSun":              "RestrictSunGoal",
    "PathfinderGoalFleeSun":                  "FleeSunGoal",
    "PathfinderGoalWaterJumping":             "DolphinJumpGoal",
    "PathfinderGoalBreed":                    "BreedGoal",
    "PathfinderGoalTempt":                    "TemptGoal",
    "PathfinderGoalEatTile":                  "EatGrassGoal",
    "PathfinderGoalBeg":                      "BegGoal",
    "PathfinderGoalTradeWithPlayer":          "TradeWithPlayerGoal",
    "PathfinderGoalLookAtPlayer":             "LookAtPlayerGoal",
    "PathfinderGoalLookAtTradingPlayer":      "LookAtCustomerGoal",
    "PathfinderGoalRandomLookaround":         "RandomLookAroundGoal",
    "PathfinderGoalRandomStroll":             "RandomStrollGoal",
    "PathfinderGoalRandomSwim":               "RandomSwimmingGoal",
    "PathfinderGoalWaterAvoidingRandomStroll":"WaterAvoidingRandomStrollGoal",
    "PathfinderGoalSit":                      "SitGoal",
    "PathfinderGoalHurtByTarget":             "HurtByTargetGoal",
    "PathfinderGoalNearestAttackableTarget":  "NearestAttackableTargetGoal",
    "PathfinderGoalDefendVillage":            "DefendVillageTargetGoal",
    "PathfinderGoalOwnerHurtByTarget":        "OwnerHurtByTargetGoal",
    "PathfinderGoalOwnerHurtTarget":          "OwnerHurtTargetGoal",
    "EntityAIFloat":           "FloatGoal",
    "EntityAISwimming":        "SwimGoal",
    "EntityAIAttackMelee":     "MeleeAttackGoal",
    "EntityAIAttackRanged":    "RangedAttackGoal",
    "EntityAIAttackRangedBow": "RangedBowAttackGoal",
    "EntityAILeapAtTarget":    "LeapAtTargetGoal",
    "EntityAIAvoidEntity":     "AvoidEntityGoal",
    "EntityAIPanic":           "PanicGoal",
    "EntityAIOpenDoor":        "OpenDoorGoal",
    "EntityAIFollowOwner":     "FollowOwnerGoal",
    "EntityAIFollowParent":    "FollowParentGoal",
    "EntityAIFollowMob":       "FollowMobGoal",
    "EntityAIBreed":           "BreedGoal",
    "EntityAITempt":           "TemptGoal",
    "EntityAIEatGrass":        "EatGrassGoal",
    "EntityAIWatchClosest":    "LookAtPlayerGoal",
    "EntityAILookIdle":        "RandomLookAroundGoal",
    "EntityAIWander":          "RandomStrollGoal",
    "EntityAIHurtByTarget":    "HurtByTargetGoal",
    "EntityAINearestAttackableTarget": "NearestAttackableTargetGoal",
    "EntityAISit":             "SitGoal",
}
_GOAL_PARENT_MAP: Dict[str, str] = {}
_GOAL_MAP_BUILT: bool = False
_ENTITY_SOURCE_MAP: Dict[str, str] = {}
def _strip_generics(name: str) -> str:
    return JavaAST.strip_generics(name)
def build_goal_inheritance_map(java_files: Dict[str, str]) -> None:
    global _GOAL_PARENT_MAP, _GOAL_MAP_BUILT, _ENTITY_SOURCE_MAP
    raw: Dict[str, str] = {}
    entity_src: Dict[str, str] = {}
    for _path, code in java_files.items():
        ast = JavaAST(code)
        ast._parse()
        if ast._tree is not None:
            for cls_decl in ast.get_class_declarations():
                entity_src[cls_decl.name] = code
            for child, parent in ast.all_class_extends():
                child  = JavaAST.strip_generics(child)
                parent = JavaAST.strip_generics(parent)
                if (child.endswith("Goal") or parent.endswith("Goal")
                        or parent in VANILLA_GOALS or child in VANILLA_GOALS
                        or parent in GOAL_NAME_ALIASES or child in GOAL_NAME_ALIASES):
                    raw[child] = GOAL_NAME_ALIASES.get(parent, parent)
        else:
            m_cls = re.search(r'\bclass\s+([A-Za-z0-9_]+)', code)
            if m_cls:
                entity_src[m_cls.group(1)] = code
            for m in re.finditer(
                r'\bclass\s+([A-Za-z0-9_]+)\s*(?:<[^>]*>)?\s+extends\s+([A-Za-z0-9_]+)\s*(?:<[^>]*>)?',
                code
            ):
                child  = _strip_generics(m.group(1))
                parent = _strip_generics(m.group(2))
                if (child.endswith("Goal") or parent.endswith("Goal")
                        or parent in VANILLA_GOALS or child in VANILLA_GOALS
                        or parent in GOAL_NAME_ALIASES or child in GOAL_NAME_ALIASES):
                    raw[child] = GOAL_NAME_ALIASES.get(parent, parent)
    _GOAL_PARENT_MAP = raw
    _ENTITY_SOURCE_MAP = entity_src
    _GOAL_MAP_BUILT = True
    custom_count = sum(1 for c in raw if c not in VANILLA_GOALS)
    print(f"[goal-map] Built inheritance map: {len(raw)} entries "
          f"({custom_count} custom, {len(raw) - custom_count} vanilla)")
def resolve_custom_goal(custom_class: str, visited: Optional[Set[str]] = None) -> Optional[str]:
    if visited is None:
        visited = set()
    if custom_class in visited:
        return None
    visited.add(custom_class)
    if custom_class in GOAL_NAME_ALIASES:
        resolved = GOAL_NAME_ALIASES[custom_class]
        print(f"{custom_class} -> {resolved} (alias)")
        return resolved
    if custom_class in VANILLA_GOALS:
        return custom_class
    parent = _GOAL_PARENT_MAP.get(custom_class)
    if not parent:
        return None
    if parent in VANILLA_GOALS:
        print(f"{custom_class} -> {parent} (vanilla)")
        return parent
    print(f"{custom_class} -> {parent} (custom, descending...)")
    return resolve_custom_goal(parent, visited)
def _collect_super_goals(entity_class: str,
                         java_files: Dict[str, str],
                         visited: Optional[Set[str]] = None) -> List[str]:
    if visited is None:
        visited = set()
    if entity_class in visited:
        return []
    visited.add(entity_class)
    BASE_ENTITY_CLASSES = {
        "Mob", "PathfinderMob", "Animal", "Monster", "AmbientCreature",
        "WaterAnimal", "AbstractFish", "Creature", "AbstractVillager",
        "TamableAnimal", "AbstractGolem", "AbstractSkeleton",
        "AbstractZombie", "Slime", "Ghast", "FlyingMob",
    }
    src = _ENTITY_SOURCE_MAP.get(entity_class)
    if not src:
        for _path, code in java_files.items():
            ast_check = JavaAST(code)
            ast_check._parse()
            if ast_check._tree is not None:
                if any(d.name == entity_class for d in ast_check.get_class_declarations()):
                    src = code
                    break
            elif re.search(rf'\bclass\s+{re.escape(entity_class)}\b', code):
                src = code
                break
    if not src:
        return []
    parent_entity = None
    ast_src = JavaAST(src)
    ast_src._parse()
    if ast_src._tree is not None:
        parent_entity = ast_src.superclass_name(entity_class)
        if parent_entity:
            parent_entity = JavaAST.strip_generics(parent_entity)
    else:
        parent_m = re.search(
            r'\bclass\s+' + re.escape(entity_class) + r'\s*(?:<[^>]*>)?\s+extends\s+([A-Za-z0-9_]+)',
            src
        )
        if parent_m:
            parent_entity = parent_m.group(1)
    if not parent_entity or parent_entity in BASE_ENTITY_CLASSES:
        return []
    parent_src = _ENTITY_SOURCE_MAP.get(parent_entity)
    if not parent_src:
        for _path, code in java_files.items():
            ast_check = JavaAST(code)
            ast_check._parse()
            if ast_check._tree is not None:
                if any(d.name == parent_entity for d in ast_check.get_class_declarations()):
                    parent_src = code
                    break
            elif re.search(rf'\bclass\s+{re.escape(parent_entity)}\b', code):
                parent_src = code
                break
    if not parent_src:
        return []
    inherited: List[str] = []
    inherited.extend(extract_ai_goals_from_java(parent_src))
    parent_ast = JavaAST(parent_src)
    parent_ast._parse()
    calls_super = False
    if parent_ast._tree is not None:
        for _, inv in parent_ast._tree.filter(javalang.tree.MethodInvocation):
            if inv.member == 'registerGoals' and getattr(inv, 'qualifier', '') == 'super':
                calls_super = True
                break
    else:
        calls_super = bool(re.search(r'\bsuper\s*\.\s*registerGoals\s*\(\s*\)', parent_src))
    if calls_super:
        inherited.extend(_collect_super_goals(parent_entity, java_files, visited))
    return inherited
def extract_ai_goals_from_java(java_code: str,
                                extra_java_files: Optional[Dict[str, str]] = None):
    if not _GOAL_MAP_BUILT:
        build_goal_inheritance_map(extra_java_files or {"<inline>": java_code})
    java_files_ref = extra_java_files or {}
    ai_goals: List[str] = []
    def _add(goal: str):
        if goal and goal not in ai_goals:
            ai_goals.append(goal)
    ast = JavaAST(java_code)
    ast._parse()
    if ast._tree is not None:
        all_new_types = [JavaAST.strip_generics(t) for t in ast.all_object_creation_types()]
        for ctype in all_new_types:
            if ctype in VANILLA_GOALS:
                _add(ctype)
            elif ctype in GOAL_NAME_ALIASES:
                _add(GOAL_NAME_ALIASES[ctype])
        for inv in ast.invocations_of('addGoal'):
            args = getattr(inv, 'arguments', []) or []
            if len(args) >= 2:
                goal_arg = args[1]
                if isinstance(goal_arg, javalang.tree.ClassCreator):
                    cls_name = JavaAST.strip_generics(goal_arg.type.name)
                    if cls_name in VANILLA_GOALS:
                        _add(cls_name)
                    elif cls_name in GOAL_NAME_ALIASES:
                        _add(GOAL_NAME_ALIASES[cls_name])
        custom_instantiated: Set[str] = set()
        for ctype in all_new_types:
            if ctype not in VANILLA_GOALS and ctype not in GOAL_NAME_ALIASES and ctype.endswith('Goal'):
                custom_instantiated.add(ctype)
        for custom_cls in sorted(custom_instantiated):
            for child, parent in ast.all_class_extends():
                if child == custom_cls:
                    local_parent = GOAL_NAME_ALIASES.get(parent, parent)
                    if custom_cls not in _GOAL_PARENT_MAP:
                        _GOAL_PARENT_MAP[custom_cls] = local_parent
            resolved = resolve_custom_goal(custom_cls)
            if resolved:
                if resolved not in ai_goals:
                    print(f"Custom goal '{custom_cls}' resolved to '{resolved}'")
                _add(resolved)
            else:
                print(f"Custom goal '{custom_cls}' could not be resolved to a vanilla goal")
        calls_super_register = any(
            inv.member == 'registerGoals'
            for _, inv in ast._tree.filter(javalang.tree.MethodInvocation)
            if getattr(inv, 'qualifier', '') in ('', 'super')
        ) if ast._tree else False
        for _, inv in ast._tree.filter(javalang.tree.MethodInvocation):
            if inv.member == 'registerGoals' and getattr(inv, 'qualifier', '') == 'super':
                calls_super_register = True
                break
        if calls_super_register:
            entity_cls = ast.primary_class_name()
            if entity_cls:
                inherited = _collect_super_goals(entity_cls, java_files_ref)
                for g in inherited:
                    _add(g)
                if inherited:
                    print(f"Inherited {len(inherited)} goal(s) via "
                          f"super.registerGoals() for {entity_cls}: {inherited}")
    else:
        for goal_name in VANILLA_GOALS:
            if re.search(rf'\bnew\s+{re.escape(goal_name)}\s*[(<]', java_code):
                _add(goal_name)
        for alias, canonical in GOAL_NAME_ALIASES.items():
            if re.search(rf'\bnew\s+{re.escape(alias)}\s*[(<]', java_code):
                _add(canonical)
        for m in re.finditer(
            r'(?:goalSelector|targetSelector)?\s*\.?\s*addGoal\s*\(\s*\d+\s*,\s*new\s+([A-Za-z0-9_]+)\s*[(<]',
            java_code, re.DOTALL
        ):
            cls_name = _strip_generics(m.group(1))
            if cls_name in VANILLA_GOALS:
                _add(cls_name)
            elif cls_name in GOAL_NAME_ALIASES:
                _add(GOAL_NAME_ALIASES[cls_name])
        custom_instantiated = set()
        for m in re.finditer(r'\bnew\s+([A-Za-z0-9_]+Goal)\s*[(<]', java_code):
            cls_name = _strip_generics(m.group(1))
            if cls_name not in VANILLA_GOALS and cls_name not in GOAL_NAME_ALIASES:
                custom_instantiated.add(cls_name)
        for custom_cls in sorted(custom_instantiated):
            local_m = re.search(
                rf'\bclass\s+{re.escape(custom_cls)}\s*(?:<[^>]*>)?\s+extends\s+([A-Za-z0-9_]+)\s*(?:<[^>]*>)?',
                java_code
            )
            if local_m:
                local_parent = GOAL_NAME_ALIASES.get(_strip_generics(local_m.group(1)), _strip_generics(local_m.group(1)))
                if custom_cls not in _GOAL_PARENT_MAP:
                    _GOAL_PARENT_MAP[custom_cls] = local_parent
            resolved = resolve_custom_goal(custom_cls)
            if resolved:
                if resolved not in ai_goals:
                    print(f"Custom goal '{custom_cls}' resolved to '{resolved}'")
                _add(resolved)
            else:
                print(f"Custom goal '{custom_cls}' could not be resolved to a vanilla goal")
        if re.search(r'\bsuper\s*\.\s*registerGoals\s*\(\s*\)', java_code):
            cls_m = re.search(r'\bclass\s+([A-Za-z0-9_]+)', java_code)
            if cls_m:
                entity_cls = cls_m.group(1)
                inherited = _collect_super_goals(entity_cls, java_files_ref)
                for g in inherited:
                    _add(g)
                if inherited:
                    print(f"Inherited {len(inherited)} goal(s) via "
                          f"super.registerGoals() for {entity_cls}: {inherited}")
    LEGACY_EXTEND_MAP = {
        "MeleeAttackGoal", "RangedAttackGoal",
        "NearestAttackableTargetGoal", "HurtByTargetGoal",
        "AvoidEntityGoal", "PanicGoal", "FollowOwnerGoal",
    }
    ast2 = JavaAST(java_code)
    ast2._parse()
    for base in LEGACY_EXTEND_MAP:
        if ast2._tree is not None:
            for child, parent in ast2.all_class_extends():
                if parent == base:
                    if base not in ai_goals and child in [JavaAST.strip_generics(t) for t in ast2.all_object_creation_types()]:
                        _add(base)
        else:
            custom = re.search(rf'\bclass\s+(\w+)\s*(?:<[^>]*>)?\s+extends\s+{re.escape(base)}', java_code)
            if custom:
                if base not in ai_goals and re.search(rf'\bnew\s+{re.escape(custom.group(1))}\s*[(<]', java_code):
                    _add(base)
    return ai_goals
def extract_damage_immunities_from_java(java_code: str):
    immunities = set()
    projectile_types = {
        "AbstractArrow", "Arrow", "SpectralArrow", "Trident",
        "ShulkerBullet", "FireworkRocketEntity", "ThrownPotion",
        "ThrownSplashPotion", "WindCharge", "SmallFireball", "LargeFireball",
    }
    for cls in projectile_types:
        if re.search(rf'\binstanceof\s+{re.escape(cls)}\b', java_code):
            immunities.add("projectile")
            break
    if re.search(r'\binstanceof\s+(?:Player|ServerPlayer|EntityPlayer)\b', java_code):
        immunities.add("player")
    fire_patterns = [
        r'\bfireImmune\s*\(\)',
        r'fireImmune\s*=\s*true',
        r'isFireImmune\s*\(\s*\)\s*\{[^}]*return\s+true',
        r'DamageSource\.(?:ON_FIRE|IN_FIRE|LIGHTNING|HOT_FLOOR|LAVA|CAMPFIRE)',
        r'DamageTypes\.(?:ON_FIRE|IN_FIRE|LAVA|HOT_FLOOR)',
        r'"fire"\s*,',
        r'DamageSource\.f_19315_',
        r'isOnFire\s*\(\s*\)',
    ]
    for pat in fire_patterns:
        if re.search(pat, java_code, re.IGNORECASE):
            immunities.add("fire")
            break
    drown_patterns = [
        r'canBreatheUnderwater\s*\(\s*\)\s*\{[^}]*return\s+true',
        r'DamageSource\.(?:DROWN|DROWN_ING)',
        r'DamageTypes\.DROWN',
        r'"drown"',
        r'DamageSource\.f_19314_',
    ]
    for pat in drown_patterns:
        if re.search(pat, java_code, re.IGNORECASE):
            immunities.add("drown")
            break
    fall_patterns = [
        r'causeFallDamage\s*\([^)]*\)\s*\{[^}]*return\s+false',
        r'DamageSource\.(?:FALL|STALAGMITE)',
        r'DamageTypes\.FALL',
        r'"fall"',
        r'DamageSource\.f_19312_',
    ]
    for pat in fall_patterns:
        if re.search(pat, java_code, re.IGNORECASE):
            immunities.add("fall")
            break
    if re.search(r'DamageSource\.(?:EXPLOSION|GENERIC_KILL|CRAMMING)|DamageTypes\.EXPLOSION|"explosion"', java_code, re.IGNORECASE):
        immunities.add("explosion")
    magic_patterns = [
        r'DamageSource\.(?:MAGIC|WITHER|DRAGON_BREATH)',
        r'DamageTypes\.(?:MAGIC|WITHER|DRAGON_BREATH)',
        r'isMagic\s*\(\s*\)',
        r'"magic"',
        r'm_19372_\(\)',
    ]
    for pat in magic_patterns:
        if re.search(pat, java_code, re.IGNORECASE):
            immunities.add("magic")
            break
    if re.search(r'(?:witherSkull|WitherBoss|WITHER_SKULL)', java_code, re.IGNORECASE):
        immunities.add("wither")
    if re.search(
        r'isInvulnerableTo\s*\([^)]*\)\s*\{[^}]*return\s+true',
        java_code, re.DOTALL
    ):
        immunities.add("all")
    return sorted(immunities)
def detect_dynamic_bounding_procedure(java_code: str) -> Optional[str]:
    m = re.search(r'([A-Za-z0-9_]+)BoundingBoxScaleProcedure', java_code)
    if m:
        return m.group(0)
    m2 = re.search(r'([A-Za-z0-9_]+Procedure)\.execute', java_code)
    if m2:
        return m2.group(1)
    return None
def detect_despawn_ticks(java_code: str) -> Optional[int]:
    m = re.search(r'==\s*([0-9]{1,5})\)\s*{[^}]*remove\(', java_code)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    m2 = re.search(r'(?:tickCount|age|lifeTicks?)\s*[>]=?\s*([0-9]{1,5})[^;{]*(?:discard|remove|kill)\s*\(', java_code)
    if m2:
        try:
            val = int(m2.group(1))
            if 1 <= val <= 24000:
                return val
        except Exception:
            pass
    return None
def write_render_controller(entity_basename: str, namespace: str, geometry_identifier: str, uv_anim: Optional[Dict] = None) -> str:
    entity_basename_clean = sanitize_identifier(entity_basename)
    namespace_clean = sanitize_identifier(namespace)
    if geometry_identifier.startswith("geometry."):
        geom_tail = geometry_identifier.split(".", 1)[1]
        geom_ident = "geometry." + sanitize_identifier(geom_tail)
    else:
        geom_ident = "geometry." + sanitize_identifier(geometry_identifier)
    controller_id = f"controller.render.{namespace_clean}.{entity_basename_clean}"
    controller = {
        "format_version": RP_LEGACY_RENDER_FORMAT,
        "render_controllers": {
            controller_id: {
                "geometry": geom_ident,
                "textures": ["texture.default"],
                "materials": [
                    {"*": "Material.default"}
                ],
                "uv_anim": {}
            }
        }
    }
    if uv_anim:
        controller["render_controllers"][controller_id]["uv_anim"] = uv_anim
    out_path = os.path.join(RP_FOLDER, "render_controllers", f"{entity_basename_clean}.render_controllers.json")
    safe_write_json(out_path, controller)
    print(f"Wrote render controller: {out_path}")
    return controller_id
def write_rp_entity_json(entity_basename: str, namespace: str, texture_ref: str, geometry_identifier: str, animation_key: Optional[str], controller_id: str):
    entity_basename_clean = sanitize_identifier(entity_basename)
    namespace_clean = sanitize_identifier(namespace)
    texture_path = texture_ref_to_rp_path(texture_ref, default_kind="entity")
    if not texture_path.startswith("textures/"):
        texture_path_with_prefix = f"textures/{texture_path}"
    else:
        texture_path_with_prefix = texture_path
    if geometry_identifier.startswith("geometry."):
        geom_tail = geometry_identifier.split(".", 1)[1]
        geom_ident = "geometry." + sanitize_identifier(geom_tail)
    else:
        geom_ident = "geometry." + sanitize_identifier(geometry_identifier)
    description = {
        "identifier": f"{namespace_clean}:{entity_basename_clean}",
        "textures": {"default": texture_path_with_prefix},
        "geometry": {"default": geom_ident},
        "render_controllers": [controller_id],
        "materials": {"default": "entity_alphatest"}
    }
    client_entity = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:client_entity": {"description": description}
    }
    out_path = os.path.join(RP_FOLDER, "entity", f"{entity_basename_clean}.entity.json")
    safe_write_json(out_path, client_entity)
    print(f"[rp_entity] Wrote {out_path}")
def extract_block_properties_from_java(java_code: str):
    props = {
        "destroy_time": None,
        "explosion_resistance": None,
        "material": None,
        "texture_hint": None,
        "loot_table": None,
        "light_emission": 0,
        "friction": 0.6,
        "is_solid": True,
        "is_opaque": True,
    }
    _float_pat = r'[-+]?[0-9]*\.?[0-9]+[FfDd]?'
    m = re.search(rf'\.strength\s*\(\s*({_float_pat})(?:\s*,\s*({_float_pat}))?\s*\)', java_code)
    if m:
        try: props["destroy_time"] = float(re.sub(r'[FfDd]$', '', m.group(1)))
        except Exception: pass
        if m.group(2):
            try: props["explosion_resistance"] = float(re.sub(r'[FfDd]$', '', m.group(2)))
            except Exception: pass
    m_dt = re.search(r'\.destroyTime\s*\(\s*([-+]?[0-9]*\.?[0-9]+[FfDd]?)\s*\)', java_code)
    if m_dt and props["destroy_time"] is None:
        try: props["destroy_time"] = float(re.sub(r'[FfDd]$', '', m_dt.group(1)))
        except Exception: pass
    m_h = re.search(r'\.hardness\s*\(\s*([-+]?[0-9]*\.?[0-9]+[FfDd]?)\s*\)', java_code)
    if m_h and props["destroy_time"] is None:
        try: props["destroy_time"] = float(re.sub(r'[FfDd]$', '', m_h.group(1)))
        except Exception: pass
    m2 = re.search(r'(?:explosionResistance|explosion_resistance|explosionResistant|resistance)\s*\(?\s*([0-9]+(?:\.[0-9]+)?)\s*\)?', java_code)
    if m2 and props["explosion_resistance"] is None:
        try: props["explosion_resistance"] = float(m2.group(1))
        except Exception: pass
    m3 = re.search(r'Material\.([A-Z_]+)', java_code)
    if m3:
        props["material"] = m3.group(1).lower()
    m_ll_lambda = re.search(r'\.lightLevel\s*\(\s*(?:state\s*->|[a-z]+\s*->)\s*([0-9]+)\s*\)', java_code)
    if m_ll_lambda:
        try: props["light_emission"] = min(15, int(m_ll_lambda.group(1)))
        except Exception: pass
    if not props["light_emission"]:
        m_ll = re.search(r'\.lightLevel\s*\(\s*([0-9]+)\s*\)', java_code)
        if m_ll:
            try: props["light_emission"] = min(15, int(m_ll.group(1)))
            except Exception: pass
    if not props["light_emission"]:
        m_le = re.search(r'\.lightEmission\s*\(\s*([0-9]+)\s*\)', java_code)
        if m_le:
            try: props["light_emission"] = min(15, int(m_le.group(1)))
            except Exception: pass
    m4 = re.search(r'(?:slipperiness|friction)\s*\(?\s*([0-9]+(?:\.[0-9]+)?)\s*\)?', java_code)
    if m4:
        try: props["friction"] = float(m4.group(1))
        except Exception: pass
    m_rn = re.search(r'setRegistryName\s*\(\s*["\']([a-z0-9_:-]+)["\']', java_code, re.I)
    if m_rn:
        props["texture_hint"] = m_rn.group(1).split(":")[-1]
    else:
        m_rl = re.search(r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_:-]+)["\']', java_code, re.I)
        if m_rl:
            props["texture_hint"] = m_rl.group(1).split(":")[-1]
    m6 = re.search(r'getLootTable\(\)\s*.*?["\']([a-z0-9_:-/]+)["\']', java_code, re.I | re.DOTALL)
    if m6:
        props["loot_table"] = m6.group(1)
    m7 = re.search(r'lootTable\(\s*["\']([a-z0-9_:-/]+)["\']', java_code, re.I)
    if m7:
        props["loot_table"] = m7.group(1)
    if re.search(r'\.noOcclusion\(\)|noCollission\(\)|noOcclusionBlock\(\)', java_code):
        props["is_opaque"] = False
    if re.search(r'\.noCollission\(\)|noCollision\(\)', java_code):
        props["is_solid"] = False
    return props
def convert_java_block_to_bedrock(java_path: str, namespace: str):
    try:
        with open(java_path, 'r', encoding='utf-8', errors='ignore') as f:
            java_code = f.read()
    except Exception as e:
        print(f" Failed to read block java {java_path}: {e}")
        return
    block_basename = os.path.splitext(os.path.basename(java_path))[0]
    block_id = f"{sanitize_identifier(namespace)}:{sanitize_identifier(block_basename)}"
    props = extract_block_properties_from_java(java_code)
    block_json = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:block": {
            "description": {
                "identifier": block_id,
                "is_experimental": False,
                "register_to_creative_menu": True
            },
            "components": {}
        }
    }
    comps = block_json["minecraft:block"]["components"]
    comps["minecraft:destroy_time"] = props.get("destroy_time") if props.get("destroy_time") is not None else 1.5
    comps["minecraft:explosion_resistance"] = props.get("explosion_resistance") if props.get("explosion_resistance") is not None else 6.0
    texture_ref = resolve_texture_reference(namespace, props.get("texture_hint"), "blocks", fallback_name=sanitize_identifier(block_basename))
    comps["minecraft:material_instances"] = {"*": {"texture": texture_ref, "render_method": "opaque"}}
    if props.get("loot_table"):
        comps["minecraft:loot"] = {"table": props["loot_table"]}
    else:
        comps["minecraft:loot"] = {"table": f"loot_tables/blocks/{sanitize_identifier(block_basename)}.json"}
    comps["_converter_metadata"] = {"source_java_file": os.path.basename(java_path), "parsed_props": props}
    out_path = os.path.join(BP_FOLDER, "blocks", f"{sanitize_identifier(block_basename)}.json")
    safe_write_json(out_path, block_json)
    print(f"Converted block {java_path} -> {out_path}")
def extract_item_properties_from_java(java_code: str):
    props = {
        "max_stack_size": None,
        "durability": None,
        "texture_hint": None,
        "creative_tab": None,
        "registry_name": None,
        "is_food": False,
        "nutrition": 0,
        "saturation": 0.0,
        "is_armor": False,
        "armor_slot": None,
        "is_weapon": False,
        "attack_damage": 0,
        "is_tool": False,
    }
    for pat in [
        r'\.stacksTo\s*\(\s*([0-9]+)\s*\)',
        r'maxStackSize\s*\(\s*([0-9]+)\s*\)',
        r'setMaxStackSize\s*\(\s*([0-9]+)\s*\)',
        r'stack(?:Size|_size)\s*[=:]\s*([0-9]+)',
    ]:
        m = re.search(pat, java_code, re.I)
        if m:
            try: props["max_stack_size"] = int(m.group(1)); break
            except Exception: pass
    for pat in [
        r'\.defaultMaxDamage\s*\(\s*([0-9]+)\s*\)',
        r'\.durability\s*\(\s*([0-9]+)\s*\)',
        r'maxDamage\s*\(\s*([0-9]+)\s*\)',
        r'setMaxDamage\s*\(\s*([0-9]+)\s*\)',
        r'(?:DURABILITY|MAX_DAMAGE)\s*[=:]\s*([0-9]+)',
    ]:
        m = re.search(pat, java_code, re.I)
        if m:
            try: props["durability"] = int(m.group(1)); break
            except Exception: pass
    for pat in [
        r'setRegistryName\s*\(\s*["\']([a-z0-9_:-]+)["\']',
        r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_:-]+)["\']\s*\)',
        r'ResourceLocation\s*\(\s*["\'][^"\']+["\']\s*,\s*["\']([a-z0-9_/:-]+)["\']',
    ]:
        m = re.search(pat, java_code, re.I)
        if m:
            raw = m.group(1)
            props["registry_name"] = raw
            props["texture_hint"] = raw.split(":")[-1]
            break
    for pat in [
        r'ItemGroup\.([A-Z0-9_]+)',
        r'CreativeModeTab\.([A-Z0-9_]+)',
        r'\.tab\s*\(\s*(?:[A-Za-z0-9_]+\.)+([A-Z0-9_]+)\s*\)',
        r'creativeModeTab\s*\(\s*(?:[A-Za-z0-9_]+\.)+([A-Z0-9_]+)\s*\)',
    ]:
        m = re.search(pat, java_code)
        if m:
            props["creative_tab"] = m.group(1).lower()
            break
    if re.search(r'FoodProperties|\.food\s*\(|nutrition|saturationMod|extends\s+(?:ItemFood|BowlFoodItem)', java_code, re.I):
        props["is_food"] = True
        m3 = re.search(r'nutrition\s*\(?\s*(\d+)', java_code, re.I)
        if m3: props["nutrition"] = int(m3.group(1))
        m4 = re.search(r'saturation(?:Modifier|Mod)?\s*\(?\s*([0-9.]+)', java_code, re.I)
        if m4: props["saturation"] = float(m4.group(1))
    slot_map = {
        r'EquipmentSlot\.HEAD|ArmorItem.*HEAD': "slot.armor.head",
        r'EquipmentSlot\.CHEST|ArmorItem.*CHEST': "slot.armor.chest",
        r'EquipmentSlot\.LEGS|ArmorItem.*LEGS': "slot.armor.legs",
        r'EquipmentSlot\.FEET|ArmorItem.*FEET': "slot.armor.feet",
    }
    for pat, slot in slot_map.items():
        if re.search(pat, java_code, re.I):
            props["is_armor"] = True
            props["armor_slot"] = slot
            break
    if re.search(r'SwordItem|TieredItem|extends.*Sword|ATTACK_DAMAGE_MODIFIER', java_code, re.I):
        props["is_weapon"] = True
        m5 = re.search(r'attackDamage\s*[=+]+\s*([0-9.]+)|ATTACK_DAMAGE\s*[=:]\s*([0-9.]+)', java_code, re.I)
        if m5:
            try: props["attack_damage"] = float(m5.group(1) or m5.group(2))
            except Exception: pass
    if re.search(r'PickaxeItem|ShovelItem|AxeItem|HoeItem|DiggerItem|extends.*Tool', java_code, re.I):
        props["is_tool"] = True
    return props
def convert_java_item_to_bedrock(java_path: str, namespace: str):
    try:
        with open(java_path, 'r', encoding='utf-8', errors='ignore') as f:
            java_code = f.read()
    except Exception as e:
        print(f" Failed to read item java {java_path}: {e}")
        return
    item_basename = os.path.splitext(os.path.basename(java_path))[0]
    item_id = f"{sanitize_identifier(namespace)}:{sanitize_identifier(item_basename)}"
    props = extract_item_properties_from_java(java_code)
    bp_item = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:item": {
            "description": {"identifier": item_id, "register_to_creative_menu": True},
            "components": {}
        }
    }
    comps = bp_item["minecraft:item"]["components"]
    comps["minecraft:max_stack_size"] = props.get("max_stack_size") if props.get("max_stack_size") is not None else 64
    if props.get("durability") is not None:
        comps["minecraft:durability"] = {"max_durability": props["durability"]}
    comps["_converter_metadata"] = {"source_java_file": os.path.basename(java_path), "parsed_props": props}
    out_bp = os.path.join(BP_FOLDER, "items", f"{sanitize_identifier(item_basename)}.json")
    safe_write_json(out_bp, bp_item)
    print(f"Converted item (BP) {java_path} -> {out_bp}")
    texture_ref = resolve_texture_reference(namespace, props.get("texture_hint"), "items", fallback_name=sanitize_identifier(item_basename))
    rp_item = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:item": {
            "description": {"identifier": item_id, "category": props.get("creative_tab") or "misc"},
            "components": {"minecraft:icon": texture_ref}
        }
    }
    out_rp = os.path.join(RP_FOLDER, "items", f"{sanitize_identifier(item_basename)}.item.json")
    safe_write_json(out_rp, rp_item)
    print(f"Converted item (RP) {java_path} -> {out_rp}")
NON_ENTITY_KEYWORDS = [
    "renderer", "render", "model", "procedure", "tickupdate", "factory",
    "packet", "handler", "provider", "command", "ui", "screen", "container",
    "event", "client", "server", "loader", "registry", "setup",
    "capability", "config", "network", "message", "gui", "recipe",
    "serializer", "codec", "datafixer", "loot", "structure"
]
ENTITY_OVERRIDE_KEYWORDS = ["entity", "mob", "monster", "creature", "animal", "boss", "npc"]
_ENTITY_SUPERCLASSES = {
    'Entity', 'Mob', 'Monster', 'Animal', 'PathfinderMob',
    'TamableAnimal', 'TameableAnimal',
    'CreatureEntity', 'LivingEntity', 'MobEntity',
    'WaterAnimal', 'AmbientCreature', 'FlyingMob',
    'AbstractGolem', 'AbstractVillager', 'AbstractPiglin', 'AbstractSkeleton',
    'Projectile', 'AbstractArrow',
    'AbstractNeutralMob', 'AbstractHurtingProjectile',
    'FireworkRocketEntity', 'ThrowableProjectile', 'ThrowableItemProjectile',
    'AbstractFish', 'AbstractSchoolingFish', 'AbstractChestedHorse',
    'AbstractHorse', 'AbstractIllager', 'AbstractRaider', 'AbstractZombie',
    'SpellcasterIllager', 'PatrollingMonster', 'Slime', 'Ghast',
    'Ageable', 'AgeableMob', 'AbstractCreature',
    'ShoulderRidingEntity', 'OcelotBase',
    'NeoForgeEntity', 'NeoForgeMob', 'ForgeEntity',
    'HostileEntity', 'PassiveEntity', 'AnimalEntity', 'WaterCreatureEntity',
    'FlyingEntity', 'BlazeEntity', 'SlimeEntity', 'GolemEntity',
}
_ENTITY_METHOD_NAMES = {
    'registerGoals', 'defineSynchedData', 'createAttributes',
    'getAddEntityPacket', 'getDefaultAttributes', 'createMobAttributes',
    'createNavigation', 'createBodyControl', 'createMonsterAttributes',
    'createAnimalAttributes', 'createLivingAttributes',
    'initializeClient', 'onAddedToWorld', 'onRemovedFromWorld',
}
def is_likely_entity(java_code: str, filename: str) -> bool:
    fname = os.path.basename(filename).lower()
    has_override = any(k in fname for k in ENTITY_OVERRIDE_KEYWORDS)
    if not has_override:
        for k in NON_ENTITY_KEYWORDS:
            if k in fname:
                return False
    cls = extract_class_name(java_code) or ""
    if cls.lower().endswith("entity"):
        return True
    _SUPERCLASS_SUFFIXES = (
        "Entity", "Mob", "Monster", "Animal", "Creature",
        "Npc", "Boss", "Guardian", "Dragon", "Golem",
    )
    ast = JavaAST(java_code)
    ast._parse()
    if ast._tree is not None:
        for child, parent in ast.all_class_extends():
            parent_clean = JavaAST.strip_generics(parent)
            if parent_clean in _ENTITY_SUPERCLASSES:
                return True
            if any(parent_clean.endswith(sfx) for sfx in _SUPERCLASS_SUFFIXES):
                if ast.method_names() & _ENTITY_METHOD_NAMES:
                    return True
        if ast.method_names() & _ENTITY_METHOD_NAMES:
            return True
        for ctype in ast.all_object_creation_types():
            ctype_clean = JavaAST.strip_generics(ctype)
            if ctype_clean in _ENTITY_SUPERCLASSES:
                return True
            if ctype_clean.endswith("Entity") or ctype_clean.endswith("Mob"):
                if ast.method_names() & _ENTITY_METHOD_NAMES:
                    return True
        if _ENTITY_SOURCE_MAP:
            parent_name: Optional[str] = None
            if ast._tree is not None:
                for _c, _p in ast.all_class_extends():
                    parent_name = JavaAST.strip_generics(_p)
                    break
            else:
                _m = re.search(r'extends\s+([A-Za-z0-9_]+)', java_code)
                parent_name = _m.group(1) if _m else None
            _visited: Set[str] = set()
            while parent_name and parent_name not in _visited and len(_visited) < 8:
                _visited.add(parent_name)
                if parent_name in _ENTITY_SUPERCLASSES:
                    return True
                if parent_name in _ENTITY_SOURCE_MAP:
                    _pcode = _ENTITY_SOURCE_MAP[parent_name]
                    _past = JavaAST(_pcode)
                    _past._parse()
                    if _past._tree is not None:
                        if _past.method_names() & _ENTITY_METHOD_NAMES:
                            return True
                        _next_parent: Optional[str] = None
                        for _c2, _p2 in _past.all_class_extends():
                            _next_parent = JavaAST.strip_generics(_p2)
                            break
                        parent_name = _next_parent
                    else:
                        if any(re.search(p, _pcode) for p in [
                            r'\bregisterGoals\s*\(', r'\bcreateAttributes\s*\(',
                            r'\bcreateNavigation\s*\(', r'\bdefineSynchedData\s*\('
                        ]):
                            return True
                        _m2 = re.search(r'extends\s+([A-Za-z0-9_]+)', _pcode)
                        parent_name = _m2.group(1) if _m2 else None
                else:
                    break
        return False
    exact_names = "|".join(re.escape(n) for n in sorted(_ENTITY_SUPERCLASSES, key=len, reverse=True))
    if re.search(rf'extends\s+(?:[A-Za-z0-9_<>.,\s]*\b(?:{exact_names})\b)', java_code):
        return True
    if re.search(
        r'extends\s+[A-Za-z0-9_]+(?:Entity|Mob|Monster|Animal|Creature|Boss|Golem|Npc|Guardian)\b',
        java_code
    ):
        pass
    entity_methods = [
        r'\bregisterGoals\s*\(',
        r'\bdefineSynchedData\s*\(',
        r'\bcreateAttributes\s*\(',
        r'\bgetAddEntityPacket\s*\(',
        r'\bgetDefaultAttributes\s*\(',
        r'\bcreateMobAttributes\s*\(',
        r'\bcreateMonsterAttributes\s*\(',
        r'\bcreateAnimalAttributes\s*\(',
        r'\bcreateNavigation\s*\(',
        r'\bcreateBodyControl\s*\(',
        r'EntityType\.Builder\.of\b',
        r'\binitializeClient\s*\(',
        r'net\.neoforged\.[a-z.]+Entity',
        r'@EventBusSubscriber\b',
        r'extends\s+GeoEntity\b',
        r'GeoEntityRenderer\b',
        r'extends\s+HostileEntity\b',
        r'extends\s+PassiveEntity\b',
        r'extends\s+AnimalEntity\b',
    ]
    for pat in entity_methods:
        if re.search(pat, java_code):
            return True
    return False
def extract_entity_texture_hint(java_code: str, entity_basename: Optional[str] = None) -> Optional[str]:
    def _first_likely(candidates):
        for c in candidates:
            if c and is_probable_texture(c, entity_basename):
                return c
        return None
    for pat in [
        r'getTextureResource\s*\([^)]*\)[^{]*\{[^}]*new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
        r'getTextureLocation\s*\([^)]*\)[^{]*\{[^}]*new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
    ]:
        m = re.search(pat, java_code, re.DOTALL)
        if m:
            candidate = f"{m.group(1)}:{m.group(2)}"
            if is_probable_texture(candidate, entity_basename):
                return candidate
    for pat in [
        r'getTextureResource\s*\([^)]*\)[^{]*\{[^}]*new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*\)',
        r'getTextureLocation\s*\([^)]*\)[^{]*\{[^}]*new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*\)',
    ]:
        m = re.search(pat, java_code, re.DOTALL)
        if m:
            candidate = m.group(1)
            if is_probable_texture(candidate, entity_basename):
                return candidate
    texture_field_patterns = [
        r'(?:TEXTURE|TEXTURE_LOCATION|LAYER_0|TEXTURE_LOC|MODEL_LOCATION|SKIN)\s*=\s*new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
        r'(?:TEXTURE|TEXTURE_LOCATION|LAYER_0|TEXTURE_LOC)\s*=\s*new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*\)',
        r'(?:TEXTURE|TEXTURE_PATH|TEXTURE_NAME)\s*=\s*["\']([^"\']{4,})["\']',
    ]
    for pat in texture_field_patterns:
        m = re.search(pat, java_code, re.IGNORECASE)
        if m:
            candidate = f"{m.group(1)}:{m.group(2)}" if m.lastindex and m.lastindex >= 2 else m.group(1)
            if is_probable_texture(candidate, entity_basename):
                return candidate
    m = re.search(r'setTexture\s*\(\s*["\']([^"\']+)["\']', java_code)
    if m:
        candidate = m.group(1)
        if is_probable_texture(candidate, entity_basename):
            return candidate
    for m in re.finditer(
        r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_:-]+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
        java_code, re.IGNORECASE
    ):
        candidate = f"{m.group(1)}:{m.group(2)}"
        if is_probable_texture(candidate, entity_basename):
            return candidate
    for m in re.finditer(
        r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_:/-][^"\']*)["\']',
        java_code, re.IGNORECASE
    ):
        candidate = m.group(1)
        if is_probable_texture(candidate, entity_basename):
            return candidate
    m = re.search(r'TEXTURE[^\n\r]*?["\']([A-Za-z0-9_:/\-\.]+)["\']', java_code)
    if m:
        candidate = m.group(1)
        if is_probable_texture(candidate, entity_basename):
            return candidate
    for m in re.finditer(r'["\']([^"\']*(?:textures/|\.png)[^"\']*)["\']', java_code, re.IGNORECASE):
        candidate = m.group(1)
        if is_probable_texture(candidate, entity_basename):
            return candidate
    return None
def is_probable_texture(candidate: Optional[str], entity_basename: Optional[str] = None) -> bool:
    if not candidate:
        return False
    candidate = str(candidate)
    if "textures/" in candidate.lower() or candidate.lower().endswith(".png"):
        return True
    if re.search(r'(blocks|items|entity|textures)[\/:]', candidate, re.I):
        return True
    name = candidate.split(":")[-1].replace(".png", "")
    probes = [f"entity/{name}", f"items/{name}", f"blocks/{name}", f"{name}"]
    for p in probes:
        if rp_texture_exists(p):
            return True
    sound_indicators = ["sound", "sounds", "whisper", "sfx", "ambient", "step", "attack", "wraith", "growl", "roar"]
    if any(k in candidate.lower() for k in sound_indicators) and not "/" in candidate:
        return False
    if ":" in candidate and "/" in candidate:
        return True
    if entity_basename and entity_basename.lower() in candidate.lower():
        return True
    return False
def _find_related_code(cls_name: str) -> Optional[str]:
    target = cls_name.lower()
    for path, code in _ALL_JAVA_FILES.items():
        fname_stem = os.path.splitext(os.path.basename(path))[0].lower()
        if fname_stem == target:
            return code
        declared = extract_class_name(code)
        if declared and declared.lower() == target:
            return code
    return None
def _referenced_class_names(code: str) -> List[str]:
    found: List[str] = []
    for m in re.finditer(
        r'EntityRenderers\.register\s*\([^,)]+,\s*([A-Z][A-Za-z0-9_]+)\s*::',
        code
    ):
        found.append(m.group(1))
    for m in re.finditer(
        r'(?:bindEntityRenderer|registerEntityRenderingHandler)\s*\([^,)]+,\s*([A-Z][A-Za-z0-9_]+)',
        code
    ):
        found.append(m.group(1))
    for m in re.finditer(r'(?:setModel|this\.model)\s*\(?.*?new\s+([A-Z][A-Za-z0-9_]+)', code, re.DOTALL):
        found.append(m.group(1))
    for m in re.finditer(
        r'extends\s+\w+Renderer\s*<[^,>]+,\s*([A-Z][A-Za-z0-9_]+)',
        code
    ):
        found.append(m.group(1))
    for m in re.finditer(
        r'import\s+[\w.]+\.((?:[A-Z][A-Za-z0-9_]*)?(?:Renderer|Model|Layer))\s*;',
        code
    ):
        found.append(m.group(1))
    for m in re.finditer(
        r'extends\s+Geo\w+Renderer\s*<([A-Z][A-Za-z0-9_]+)>',
        code
    ):
        found.append(m.group(1) + "Model")
    return list(dict.fromkeys(found))
def _resolve_tex_hint_to_ref(hint: Optional[str], namespace: str, entity_basename: str) -> Optional[str]:
    if not hint:
        return None
    ns = sanitize_identifier(namespace) or "converted"
    candidate = hint.split(":")[-1].replace(".png", "").strip("/")
    if candidate.startswith("textures/"):
        candidate = candidate[len("textures/"):]
    for probe in [
        candidate,
        f"entity/{candidate}",
        f"entity/{os.path.basename(candidate)}",
        f"entity/{entity_basename}",
    ]:
        probe = probe.replace("\\", "/")
        if rp_texture_exists(probe):
            return f"{ns}:{probe}"
    return None
def find_entity_assets_aggressively(
    java_code: str,
    entity_basename: str,
    namespace: str,
    entity_cls: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    ns       = sanitize_identifier(namespace) or "converted"
    ent_toks = _camel_tokens(entity_basename)
    if entity_cls:
        ent_toks = ent_toks | _camel_tokens(entity_cls)
    ent_toks -= _ASSET_NOISE
    if not ent_toks:
        ent_toks = _camel_tokens(entity_basename)
    def _tex_ref_from_hint(hint: Optional[str]) -> Optional[str]:
        if not hint:
            return None
        candidate = hint.split(":")[-1].replace(".png", "").strip("/")
        if candidate.startswith("textures/"):
            candidate = candidate[len("textures/"):]
        for probe in [candidate, f"entity/{candidate}", f"entity/{os.path.basename(candidate)}"]:
            if rp_texture_exists(probe):
                return f"{ns}:{probe}"
        if "/" in candidate or "." in candidate:
            return f"{ns}:{candidate}"
        return None
    def _geom_from_code(code: str) -> Optional[str]:
        result = find_model_geometry_in_code(code)
        if not result:
            return None
        ns_hint, geom_name = result
        return f"geometry.{sanitize_identifier(ns_hint or namespace)}.{sanitize_identifier(geom_name)}"
    def _best_texture_on_disk() -> Optional[str]:
        best_score, best_ref = 0.0, None
        for rel_no_ext, _ in _RP_ASSET_INDEX.get("textures", []):
            score = _asset_score(ent_toks, rel_no_ext)
            if rel_no_ext.startswith("entity/"):
                score += 0.15
            if score > best_score and score >= 0.30:
                best_score = score
                best_ref   = f"{ns}:{rel_no_ext}"
        return best_ref
    def _best_geometry_on_disk() -> Optional[str]:
        best_score, best_ident = 0.0, None
        for ident, _ in _RP_ASSET_INDEX.get("geometry", []):
            ident_lower = ident.lower()
            skip_keywords = [
                "spawn_egg",
                "glass", "stone", "wood", "brick", "ore", "concrete", "sand", "dirt", "grass",
                "item", "tool", "weapon", "armor", "bow", "sword", "pickaxe", "axe", "shovel", "hoe",
                "cube", "box", "plane", "simple", "basic", "block",
                "slab", "stair", "fence", "door", "gate", "lamp", "lamp", "button"
            ]
            if any(kw in ident_lower for kw in skip_keywords):
                continue
            tail  = ident.replace("geometry.", "")
            score = _asset_score(ent_toks, tail)
            if score > best_score and score >= 0.40:
                best_score = score
                best_ident = ident
        return best_ident
    def _try_codes(codes_and_labels):
        tex, geom = None, None
        for label, code in codes_and_labels:
            if not tex:
                raw = extract_entity_texture_hint(code, entity_basename)
                tex = _tex_ref_from_hint(raw)
                if tex:
                    print(f"[assets] Texture found in {label}: {tex}")
            if not geom:
                geom = _geom_from_code(code)
                if geom:
                    print(f"[assets] Geometry found in {label}: {geom}")
            if tex and geom:
                break
        return tex, geom
    tex_ref, geom_ident = _try_codes([("entity file", java_code)])
    if not (tex_ref and geom_ident):
        candidates_cls = list(dict.fromkeys(filter(None, [
            entity_cls,
            entity_basename,
            "".join(w.capitalize() for w in entity_basename.split("_")),
        ])))
        for lookup_key in candidates_cls:
            entry = _RENDERER_MAP.get(lookup_key) or _RENDERER_MAP.get(lookup_key + "Entity")
            if not entry:
                continue
            extra: List[Tuple[str, str]] = []
            if entry.get("renderer_code"):
                extra.append((f"renderer:{entry['renderer']}", entry["renderer_code"]))
            if entry.get("model_code"):
                extra.append((f"model:{entry['model']}", entry["model_code"]))
            if extra:
                t2, g2 = _try_codes(extra)
                tex_ref   = tex_ref   or t2
                geom_ident = geom_ident or g2
            if tex_ref and geom_ident:
                break
    if not (tex_ref and geom_ident):
        ent_lower = entity_basename.lower().replace("entity", "").strip("_")
        related_codes: List[Tuple[str, str]] = []
        for path, code in _ALL_JAVA_FILES.items():
            fname_stem = os.path.splitext(os.path.basename(path))[0].lower()
            if ent_lower and ent_lower in fname_stem and fname_stem != entity_basename.lower():
                related_codes.append((fname_stem, code))
            elif entity_cls and entity_cls in code and path not in java_code:
                cls_there = extract_class_name(code)
                if cls_there and any(kw in cls_there for kw in ("Renderer", "Model", "Layer")):
                    related_codes.append((cls_there, code))
        if related_codes:
            t3, g3 = _try_codes(related_codes[:8])
            tex_ref    = tex_ref    or t3
            geom_ident = geom_ident or g3
    if not tex_ref:
        tex_ref = _best_texture_on_disk()
        if tex_ref:
            print(f"[assets] Texture fuzzy-matched for '{entity_basename}': {tex_ref}")
    if not geom_ident:
        geom_ident = _best_geometry_on_disk()
        if geom_ident:
            print(f"[assets] Geometry fuzzy-matched for '{entity_basename}': {geom_ident}")
    return tex_ref, geom_ident
def convert_java_to_bedrock(java_path: str, entity_identifier: str, gecko_maps: dict, geom_file_map: dict, geom_ns_map: dict, anim_key_map: dict, stats: dict):
    try:
        with open(java_path, 'r', encoding='utf-8', errors='ignore') as f:
            java_code = f.read()
    except Exception as e:
        print(f" Failed to read {java_path}: {e}")
        stats["errors"].append(f"read:{java_path}:{e}")
        return
    if not is_likely_entity(java_code, java_path):
        stats["skipped_files"].append(java_path)
        return


    symbol_table = JavaSymbolTable()
    symbol_table.scan_java_file(java_code)

    parts = entity_identifier.split(":")
    namespace = sanitize_identifier(parts[0]) if parts else "converted"
    entity_name = sanitize_identifier(parts[1]) if len(parts) > 1 else sanitize_identifier("entity")
    clean_identifier = f"{namespace}:{entity_name}"
    ai_goals = extract_ai_goals_from_java(java_code)
    animations = extract_animations_from_java(java_code, namespace, entity_name)
    attributes = extract_attributes_from_java(java_code)
    immunities = extract_damage_immunities_from_java(java_code)
    bounding_proc = detect_dynamic_bounding_procedure(java_code)
    despawn_ticks = detect_despawn_ticks(java_code)
    collision_w, collision_h = 0.6, 1.8
    if bounding_proc:
        collision_w, collision_h = 2.5, 3.0
    m_dims = re.search(r'EntityDimensions\.(?:scalable|fixed)\s*\(\s*([0-9.]+)\s*,\s*([0-9.]+)', java_code)
    if m_dims:
        collision_w, collision_h = float(m_dims.group(1)), float(m_dims.group(2))
    else:
        m_dims2 = re.search(r'getDimensions[^{]*\{[^}]*\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)', java_code, re.DOTALL)
        if m_dims2:
            collision_w, collision_h = float(m_dims2.group(1)), float(m_dims2.group(2))
    bedrock_entity = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:entity": {
            "description": {"identifier": clean_identifier, "is_spawnable": True, "is_experimental": False},
            "components": {
                "minecraft:type_family": {"family": ["mob", namespace]},
                "minecraft:physics": {"has_gravity": True, "has_collision": True},
                "minecraft:collision_box": {"width": collision_w, "height": collision_h},
                "minecraft:health": {"value": int(attributes.get("health", 20)), "max": int(attributes.get("health", 20))},
                "minecraft:movement": {"value": attributes.get("movement_speed", 0.3)},
                "minecraft:navigation.walk": {"can_path_over_water": False, "avoid_water": True, "can_pass_doors": True},
                "minecraft:movement.basic": {},
                "minecraft:jump.static": {},
                "minecraft:behavior.float": {"priority": 0}
            },
            "events": {}
        }
    }


    dynamic_properties = {}
    if 'IEnergyStorage' in java_code or 'receiveEnergy' in java_code:
        dynamic_properties[f"{namespace}:energy_stored"] = {"type": "int", "default": 0}
        dynamic_properties[f"{namespace}:max_energy"] = {"type": "int", "default": 1000}
    if 'IFluidHandler' in java_code or 'fill' in java_code:
        dynamic_properties[f"{namespace}:fluid_amount"] = {"type": "int", "default": 0}
        dynamic_properties[f"{namespace}:fluid_type"] = {"type": "string", "default": ""}
    if 'IItemHandler' in java_code or 'insertItem' in java_code:
        dynamic_properties[f"{namespace}:slot_contents"] = {"type": "string", "default": "[]"}
    if dynamic_properties:
        bedrock_entity["minecraft:entity"]["description"]["properties"] = dynamic_properties
    if attributes.get("attack_damage", 0) > 0:
        bedrock_entity["minecraft:entity"]["components"]["minecraft:attack"] = {"damage": int(attributes["attack_damage"])}
    armor_value = float(attributes.get("armor", 0.0))
    damage_triggers = []
    if armor_value and armor_value != 0.0:
        reduction = min(0.80, armor_value * 0.035)
        multiplier = max(0.20, 1.0 - reduction)
        damage_triggers.append({"cause": "all", "damage_multiplier": round(multiplier, 4), "description": "converted_armor_java_scale"})
    for cause in immunities:
        if cause == "all":
            continue
        damage_triggers.append({"cause": cause, "damage_multiplier": 0.001, "description": f"converted_immunity_{cause}"})
    damage_triggers.append({"cause": "entity_attack", "deals_damage": True})
    bedrock_entity["minecraft:entity"]["components"]["minecraft:damage_sensor"] = {"triggers": damage_triggers}
    behaviors = {}
    move_speed = attributes.get("movement_speed", 0.3)
    follow_range = attributes.get("follow_range", 16.0)
    for goal in ai_goals:
        priority = JAVA_GOAL_PRIORITIES.get(goal, 10)
        if goal == "NearestAttackableTargetGoal":
            behaviors["minecraft:behavior.nearest_attackable_target"] = {
                "priority": priority,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": int(follow_range)}],
                "must_see": False,
                "reselect_targets": True
            }
        elif goal == "HurtByTargetGoal":
            behaviors["minecraft:behavior.hurt_by_target"] = {
                "priority": priority,
                "alert_same_type": False
            }
        elif goal in ("OwnerHurtByTargetGoal", "OwnerHurtTargetGoal"):
            behaviors["minecraft:behavior.owner_hurt_by_target"] = {"priority": priority}
        elif goal == "MeleeAttackGoal":
            behaviors["minecraft:behavior.melee_attack"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 2.0),
                "track_target": True,
                "require_complete_path": False
            }
        elif goal in ("RangedAttackGoal", "RangedBowAttackGoal"):
            behaviors["minecraft:behavior.ranged_attack"] = {
                "priority": priority,
                "attack_interval_min": 1.0,
                "attack_interval_max": 3.0,
                "attack_radius": min(follow_range, 15.0),
                "speed_multiplier": max(1.0, move_speed * 1.5)
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:shooter"] = {
                "def": "minecraft:arrow"
            }
        elif goal == "LeapAtTargetGoal":
            behaviors["minecraft:behavior.leap_at_target"] = {
                "priority": priority,
                "yd": 0.4
            }
        elif goal == "AvoidEntityGoal":
            behaviors["minecraft:behavior.avoid_mob_type"] = {
                "priority": priority,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": 6.0}],
                "walk_speed_multiplier": max(1.0, move_speed * 1.2),
                "sprint_speed_multiplier": max(1.2, move_speed * 2.0)
            }
        elif goal == "PanicGoal":
            behaviors["minecraft:behavior.panic"] = {
                "priority": priority,
                "speed_multiplier": max(1.25, move_speed * 2.5)
            }
        elif goal == "RunAroundLikeCrazyGoal":
            behaviors["minecraft:behavior.run_around_like_crazy"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 2.0)
            }
        elif goal == "OpenDoorGoal":
            behaviors["minecraft:behavior.open_door"] = {
                "priority": priority,
                "close_door_after": True
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_open_doors"] = True
        elif goal == "BreakDoorGoal":
            behaviors["minecraft:behavior.break_door"] = {
                "priority": priority
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_break_doors"] = True
        elif goal == "FollowOwnerGoal":
            behaviors["minecraft:behavior.follow_owner"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.5),
                "start_distance": 10.0,
                "stop_distance": 2.0
            }
        elif goal == "FollowParentGoal":
            behaviors["minecraft:behavior.follow_parent"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.1)
            }
        elif goal == "FollowMobGoal":
            behaviors["minecraft:behavior.follow_mob"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.1),
                "stop_distance": 3.0,
                "search_range": int(follow_range)
            }
        elif goal == "SitWhenOrderedToGoal":
            behaviors["minecraft:behavior.sit"] = {"priority": priority}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:is_tamed"] = {}
        elif goal == "BreedGoal":
            behaviors["minecraft:behavior.breed"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.0)
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:breedable"] = {
                "require_tame": False,
                "breeds_with": []
            }
        elif goal == "TemptGoal":
            behaviors["minecraft:behavior.tempt"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.25),
                "within_radius": 6.0,
                "can_tempt_while_leashed": False
            }
        elif goal == "FloatGoal":
            behaviors["minecraft:behavior.float"] = {"priority": priority}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "WaterAvoidingRandomStrollGoal":
            behaviors["minecraft:behavior.random_stroll"] = {
                "priority": priority,
                "speed_multiplier": move_speed,
                "xz_dist": 10,
                "y_dist": 7
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["avoid_water"] = True
        elif goal == "RandomSwimmingGoal":
            behaviors["minecraft:behavior.random_swimming"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.5),
                "xz_dist": 30,
                "y_dist": 15
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "RandomStrollGoal":
            behaviors["minecraft:behavior.random_stroll"] = {
                "priority": priority,
                "speed_multiplier": move_speed
            }
        elif goal == "LookAtPlayerGoal":
            behaviors["minecraft:behavior.look_at_player"] = {
                "priority": priority,
                "look_distance": follow_range / 2.0,
                "probability": 0.02
            }
        elif goal == "RandomLookAroundGoal":
            behaviors["minecraft:behavior.random_look_around"] = {"priority": priority}
        elif goal == "SwimGoal":
            behaviors["minecraft:behavior.float"] = {"priority": priority}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "BreatheAirGoal":
            behaviors["minecraft:behavior.move_to_water"] = {"priority": priority, "search_range": 8, "search_height": 4}
        elif goal in ("NearestAttackableTargetExpiringGoal", "ToggleableNearestAttackableTargetGoal"):
            behaviors.setdefault("minecraft:behavior.nearest_attackable_target", {
                "priority": priority, "must_see": False, "reselect_targets": True,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": int(follow_range)}]
            })
        elif goal == "NonTamedTargetGoal":
            behaviors["minecraft:behavior.nearest_attackable_target"] = {
                "priority": priority, "must_see": True,
                "entity_types": [{"filters": {"all_of": [
                    {"test": "is_family", "subject": "other", "value": "player"},
                    {"test": "is_owner", "subject": "other", "operator": "!=", "value": True}
                ]}, "max_dist": int(follow_range)}]
            }
        elif goal == "DefendVillageTargetGoal":
            behaviors["minecraft:behavior.nearest_attackable_target"] = {
                "priority": priority, "must_see": False,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "monster"}, "max_dist": int(follow_range)}]
            }
        elif goal == "ResetAngerGoal":
            bedrock_entity["minecraft:entity"]["components"].setdefault("minecraft:anger_level", {"max_anger": 20, "anger_decrement_interval": 1.0})
        elif goal == "OcelotAttackGoal":
            behaviors["minecraft:behavior.melee_attack"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 2.0), "track_target": True, "require_complete_path": False}
        elif goal == "CreeperSwellGoal":
            behaviors["minecraft:behavior.swell"] = {"priority": priority}
        elif goal == "RangedCrossbowAttackGoal":
            behaviors["minecraft:behavior.ranged_attack"] = {"priority": priority, "attack_interval_min": 1.0, "attack_interval_max": 3.0, "attack_radius": min(follow_range, 15.0), "speed_multiplier": max(1.0, move_speed * 1.5)}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:shooter"] = {"def": "minecraft:arrow"}
        elif goal == "MoveTowardsTargetGoal":
            behaviors["minecraft:behavior.move_towards_target"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.5), "within": int(follow_range)}
        elif goal == "FleeSunGoal":
            behaviors["minecraft:behavior.move_outdoors"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.2), "timeout_cooldown": 8.0}
        elif goal == "RestrictSunGoal":
            behaviors["minecraft:behavior.restrict_sun"] = {"priority": priority}
        elif goal == "InteractDoorGoal":
            behaviors["minecraft:behavior.open_door"] = {"priority": priority, "close_door_after": True}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_open_doors"] = True
        elif goal == "BreakBlockGoal":
            behaviors["minecraft:behavior.break_door"] = {"priority": priority}
        elif goal == "UseItemGoal":
            pass
        elif goal in ("MoveThroughVillageGoal", "MoveThroughVillageAtNightGoal", "ReturnToVillageGoal", "PatrolVillageGoal", "MoveTowardsRaidGoal"):
            behaviors["minecraft:behavior.move_through_village"] = {"priority": priority, "speed_multiplier": move_speed, "only_at_night": goal == "MoveThroughVillageAtNightGoal"}
        elif goal == "MoveTowardsRestrictionGoal":
            behaviors["minecraft:behavior.move_towards_restriction"] = {"priority": priority, "speed_multiplier": move_speed}
        elif goal == "MoveToBlockGoal":
            behaviors["minecraft:behavior.move_to_block"] = {"priority": priority, "speed_multiplier": move_speed, "search_range": 8, "search_height": 4, "goal_radius": 1.0}
        elif goal == "FindWaterGoal":
            behaviors["minecraft:behavior.move_to_water"] = {"priority": priority, "search_range": 8, "search_height": 4}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "RandomWalkingGoal":
            behaviors["minecraft:behavior.random_stroll"] = {"priority": priority, "speed_multiplier": move_speed}
        elif goal == "FollowBoatGoal":
            behaviors["minecraft:behavior.follow_mob"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.2), "stop_distance": 3.0, "search_range": int(follow_range)}
        elif goal == "FollowSchoolLeaderGoal":
            behaviors["minecraft:behavior.follow_mob"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.1), "stop_distance": 2.0, "search_range": int(follow_range)}
        elif goal == "LlamaFollowCaravanGoal":
            behaviors["minecraft:behavior.follow_caravan"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.2)}
        elif goal == "LandOnOwnersShoulderGoal":
            behaviors.setdefault("minecraft:behavior.float", {"priority": 0})
        elif goal == "SitGoal":
            behaviors["minecraft:behavior.sit"] = {"priority": priority}
        elif goal == "EatGrassGoal":
            behaviors["minecraft:behavior.eat_block"] = {"priority": priority, "eat_and_replace_block_pairs": [{"eat_block": "grass", "replace_block": "dirt"}], "success_chance": "0.05", "time_until_eat": 1.8}
        elif goal == "BegGoal":
            behaviors["minecraft:behavior.beg"] = {"priority": priority, "look_distance": 8.0, "look_time": 40}
        elif goal == "TradeWithPlayerGoal":
            behaviors["minecraft:behavior.trade_with_player"] = {"priority": priority}
        elif goal == "LookAtCustomerGoal":
            behaviors["minecraft:behavior.look_at_trading_player"] = {"priority": priority}
        elif goal == "ShowVillagerFlowerGoal":
            behaviors["minecraft:behavior.offer_flower"] = {"priority": priority}
        elif goal == "TriggerSkeletonTrapGoal":
            behaviors["minecraft:behavior.summon_entity"] = {"priority": priority, "summon_choices": [{"min_activation_range": 0, "max_activation_range": 16, "summon_cap": 4, "summon_cap_radius": 8.0, "weight": 10, "entity_type": "minecraft:skeleton_horse"}]}
        elif goal == "DolphinJumpGoal":
            behaviors["minecraft:behavior.jump_for_food"] = {"priority": priority}
        elif goal == "JumpGoal":
            behaviors["minecraft:behavior.jump_to_block"] = {"priority": priority, "search_width": 8, "search_height": 4, "minimum_path_length": 2}
        elif goal == "CatLieOnBedGoal":
            behaviors["minecraft:behavior.sleep"] = {"priority": priority, "sleep_collider_height": 0.3, "sleep_collider_width": 1.0, "sleep_y_offset": 0.6, "timeout_cooldown": 10.0}
        elif goal == "CatSitOnBlockGoal":
            behaviors["minecraft:behavior.move_to_block"] = {"priority": priority, "speed_multiplier": move_speed, "search_range": 8, "search_height": 4, "goal_radius": 1.0}
        elif goal == "LookAtGoal":
            behaviors["minecraft:behavior.look_at_entity"] = {"priority": priority, "look_distance": follow_range / 2.0, "probability": 0.02}
        elif goal == "LookAtWithoutMovingGoal":
            behaviors["minecraft:behavior.look_at_player"] = {"priority": priority, "look_distance": follow_range / 2.0, "probability": 0.02}
        elif goal == "LookRandomlyGoal":
            behaviors["minecraft:behavior.random_look_around"] = {"priority": priority}
    if "minecraft:behavior.float" not in behaviors:
        behaviors["minecraft:behavior.float"] = {"priority": 0}
    if behaviors:
        bedrock_entity["minecraft:entity"]["components"].update(behaviors)
    if any(g in ai_goals for g in ("SitWhenOrderedToGoal", "FollowOwnerGoal", "OwnerHurtByTargetGoal", "OwnerHurtTargetGoal")):
        bedrock_entity["minecraft:entity"]["components"].setdefault("minecraft:tameable", {
            "probability": 0.33,
            "tame_items": "bone",
            "tame_event": {"event": "minecraft:on_tame", "target": "self"}
        })
        bedrock_entity["minecraft:entity"]["components"].setdefault("minecraft:is_tamed", {})
    comps = bedrock_entity["minecraft:entity"]["components"]
    is_flyer = bool(
        re.search(r'extends\s+(?:FlyingMob|Ghast|Phantom|Bee|Parrot|AbstractFlyingEntity)', java_code, re.I) or
        re.search(r'FlyingMoveControl|setNoGravity\s*\(\s*true', java_code)
    )
    is_swimmer = bool(
        re.search(r'extends\s+(?:WaterAnimal|Squid|Dolphin|TropicalFish|AbstractFish)', java_code, re.I) or
        "RandomSwimmingGoal" in ai_goals or "FindWaterGoal" in ai_goals
    )
    is_climber = bool(re.search(r'canClimb\(\)|onClimbable|Spider|CaveSpider', java_code, re.I))
    if is_flyer and not is_swimmer:
        comps.pop("minecraft:navigation.walk", None)
        comps["minecraft:navigation.fly"] = {"can_path_over_water": True}
        comps["minecraft:movement.fly"] = {}
        comps.pop("minecraft:jump.static", None)
        comps["minecraft:can_fly"] = {}
    elif is_swimmer:
        comps["minecraft:navigation.walk"]["can_swim"] = True
        comps.setdefault("minecraft:navigation.swim", {"can_path_over_water": True})
        comps["minecraft:underwater_movement"] = {"value": round(attributes.get("movement_speed", 0.3) * 0.85, 4)}
    if is_climber:
        comps["minecraft:navigation.climb"] = {}
    generate_entity_events(bedrock_entity, ai_goals, java_code, namespace, clean_identifier, attributes)
    if despawn_ticks is not None and despawn_ticks <= 600:
        bedrock_entity["minecraft:entity"]["components"]["minecraft:timer"] = {
            "looping": False,
            "time": round(despawn_ticks / 20.0, 2),
            "time_down_event": {"event": "minecraft:entity_spawned"}
        }
    metadata = {
        "source_java_file": os.path.basename(java_path),
        "raw_attributes": attributes,
        "animations_extracted": sorted(list(animations)),
        "immunities_detected": immunities,
        "dynamic_bounding_box_procedure": bounding_proc,
        "despawn_after_ticks": despawn_ticks
    }
    bedrock_entity["minecraft:entity"]["components"]["_converter_metadata"] = metadata
    def should_loop(anim_name: str) -> bool:
        n = anim_name.lower()
        if any(k in n for k in ["idle", "chase", "walk", "run", "pose", "sit", "hover"]):
            return True
        if any(k in n for k in ["attack", "hit", "strike", "death", "slam", "bite"]):
            return False
        return True
    anim_json = {"format_version": RP_LEGACY_ANIM_FORMAT, "animations": {}}
    primary_animation_key = None
    if animations:
        for anim in sorted(animations):
            loop = should_loop(anim)
            length = 1.0 if loop else 0.5
            anim_json["animations"][anim] = {"loop": loop, "animation_length": length}
        primary_animation_key = sorted(animations)[0]
    else:
        base_id = f"animation.{namespace}.{entity_name}"
        idle_id = f"{base_id}.idle"
        anim_json["animations"][idle_id] = {"loop": True, "animation_length": 1.0}
        anim_json["animations"][f"{base_id}.walk"] = {"loop": True, "animation_length": 0.5}
        anim_json["animations"][f"{base_id}.run"] = {"loop": True, "animation_length": 0.4}
        anim_json["animations"][f"{base_id}.attack"] = {"loop": False, "animation_length": 0.5}
        primary_animation_key = idle_id
    entity_basename = sanitize_identifier(os.path.splitext(os.path.basename(java_path))[0])
    anim_json_path_rp = os.path.join(RP_FOLDER, "animations", f"{entity_basename}.animation.json")
    if not os.path.exists(anim_json_path_rp):
        safe_write_json(anim_json_path_rp, anim_json)
        print(f"[anim] Wrote stub RP animation JSON: {anim_json_path_rp}")
    else:
        print(f"[anim] Skipped stub write — GeckoLib animation already present: {anim_json_path_rp}")
    entity_json_path = os.path.join(BP_FOLDER, "entities", f"{entity_basename}.json")
    safe_write_json(entity_json_path, bedrock_entity)
    print(f"Converted (BP entity) {java_path} -> {entity_json_path}")
    stats["converted_entities_bp"].append(entity_json_path)
    java_geom_tuple = find_model_geometry_in_code(java_code)
    java_geom_identifier: Optional[str] = None
    if java_geom_tuple:
        java_ns, java_name = java_geom_tuple
        java_ns_clean = sanitize_identifier(java_ns) if java_ns else None
        java_name_clean = sanitize_identifier(java_name) if java_name else None
        java_key = (java_ns_clean, java_name_clean)
        java_key2 = (namespace.lower(), java_name_clean)
        if java_key in geom_ns_map:
            java_geom_identifier = geom_ns_map[java_key]
            print(f"[java-ref] Found Java-referenced geometry for {entity_basename}: {java_geom_identifier}")
        elif java_key2 in geom_ns_map:
            java_geom_identifier = geom_ns_map[java_key2]
            print(f"[java-ref] Found Java-referenced geometry for {entity_basename}: {java_geom_identifier}")
        elif java_name_clean in geom_file_map:
            java_geom_identifier = geom_file_map[java_name_clean]
            print(f"[java-ref] Found Java-referenced geometry for {entity_basename}: {java_geom_identifier}")
    entity_cls_name = extract_class_name(java_code)
    aggressive_tex, aggressive_geom = find_entity_assets_aggressively(
        java_code, entity_basename, namespace, entity_cls=entity_cls_name
    )
    geom_identifier: Optional[str] = None
    if java_geom_identifier:
        geom_identifier = java_geom_identifier
    entity_class_simple = os.path.splitext(os.path.basename(java_path))[0]
    geom_tuple = None
    geom_tuple = gecko_maps.get("entity_to_geometry", {}).get(entity_class_simple)
    if not geom_tuple:
        for k, v in gecko_maps.get("entity_to_geometry", {}).items():
            if (k.lower() == entity_class_simple.lower()
                    or k.lower().endswith(entity_class_simple.lower())
                    or entity_class_simple.lower().endswith(k.lower())):
                geom_tuple = v
                break
    if not geom_tuple:
        model_cls = gecko_maps.get("entity_to_model", {}).get(entity_class_simple)
        if model_cls:
            geom_tuple = gecko_maps.get("model_map", {}).get(model_cls)
    if not geom_tuple:
        for model_cls, geom in gecko_maps.get("model_map", {}).items():
            if entity_basename.lower() in model_cls.lower() or entity_basename.lower() in geom[1].lower():
                geom_tuple = geom
                break
    if geom_tuple:
        ns_hint, geom_name = geom_tuple
        if geom_name:
            geom_name_lower = geom_name.lower()
            skip_keywords = [
                "spawn_egg",
                "glass", "stone", "wood", "brick", "ore", "concrete", "sand", "dirt", "grass",
                "item", "tool", "weapon", "armor", "bow", "sword", "pickaxe", "axe", "shovel", "hoe",
                "cube", "box", "plane", "simple", "basic", "block",
                "slab", "stair", "fence", "door", "gate", "lamp", "button"
            ]
            if any(kw in geom_name_lower for kw in skip_keywords):
                geom_tuple = None
        if geom_tuple:
            ns_hint, geom_name = geom_tuple
            ns_hint_clean  = sanitize_identifier(ns_hint)  if ns_hint  else None
            geom_name_clean = sanitize_identifier(geom_name) if geom_name else None
            key  = (ns_hint_clean, geom_name_clean)
            key2 = (namespace.lower(), geom_name_clean)
            if key in geom_ns_map:
                geom_identifier = geom_ns_map[key]
            elif key2 in geom_ns_map:
                geom_identifier = geom_ns_map[key2]
            elif geom_name_clean in geom_file_map:
                geom_identifier = geom_file_map[geom_name_clean]
            else:
                for (ns_k, name_k), ident in geom_ns_map.items():
                    if name_k and geom_name_clean and name_k.endswith(geom_name_clean):
                        geom_identifier = ident
                        break
    if not geom_identifier and entity_basename.lower() in geom_file_map:
        geom_identifier = geom_file_map[entity_basename.lower()]
    if not geom_identifier:
        if aggressive_geom:
            aggressive_lower = aggressive_geom.lower()
            skip_keywords = [
                "spawn_egg",
                "glass", "stone", "wood", "brick", "ore", "concrete", "sand", "dirt", "grass",
                "item", "tool", "weapon", "armor", "bow", "sword", "pickaxe", "axe", "shovel", "hoe",
                "cube", "box", "plane", "simple", "basic", "block",
                "slab", "stair", "fence", "door", "gate", "lamp", "button"
            ]
            is_invalid = any(kw in aggressive_lower for kw in skip_keywords)
            if not is_invalid:
                geom_identifier = aggressive_geom
            elif is_invalid:
                skip_reason = "spawn_egg" if "spawn_egg" in aggressive_lower else "item/simple geometry"
                print(f"[assets] Skipping {skip_reason} for '{entity_basename}', continuing search...")
                pass
    if aggressive_tex:
        texture_ref = aggressive_tex
    else:
        texture_hint = extract_entity_texture_hint(java_code, entity_basename)
        texture_ref  = resolve_texture_reference(namespace, texture_hint, "entity", fallback_name=entity_basename)
    if not geom_identifier:
        entity_cls = extract_class_name(java_code) or entity_basename
        if _LAYERDEF_GEO_MAP:
            if entity_cls in _LAYERDEF_GEO_MAP:
                geom_identifier = _LAYERDEF_GEO_MAP[entity_cls]
            else:
                ent_stem = re.sub(r'(?i)Entity$', '', entity_cls).lower()
                for model_cls, geo_id in _LAYERDEF_GEO_MAP.items():
                    model_stem = re.sub(r'(?i)Model$', '', model_cls).lower()
                    if ent_stem and model_stem and ent_stem == model_stem:
                        geom_identifier = geo_id
                        print(f"[layerdef-link] {entity_cls} -> {model_cls} -> {geo_id}")
                        break
                if not geom_identifier:
                    geo_data = convert_layerdefinition_to_geckolib(
                        java_code, entity_basename, namespace, entity_name=entity_name
                    )
                    if geo_data:
                        out_path = os.path.join(RP_FOLDER, "geometry", f"{entity_basename}.geo.json")
                        try:
                            safe_write_json(out_path, geo_data)
                            geom_identifier = geo_data['minecraft:geometry'][0]['description']['identifier']
                            print(f"[layerdef-inline] Converted inline LayerDefinition for {entity_basename}")
                        except Exception as _le:
                            print(f"[layerdef-inline] Write failed: {_le}")
        if not geom_identifier:
            geo_data = convert_layerdefinition_to_geckolib(
                java_code, entity_basename, namespace, entity_name=entity_name
            )
            if geo_data:
                out_path = os.path.join(RP_FOLDER, "geometry", f"{entity_basename}.geo.json")
                try:
                    safe_write_json(out_path, geo_data)
                    geom_identifier = geo_data['minecraft:geometry'][0]['description']['identifier']
                    print(f"[layerdef-inline] Converted inline LayerDefinition for {entity_basename}")
                except Exception as _le:
                    print(f"[layerdef-inline] Write failed: {_le}")
    if not geom_identifier:
        geom_identifier = f"geometry.{namespace}.{entity_name}"
        stats["missing_geometry"].append((java_path, entity_basename))
        print(f"[rp-fallback] No geometry found for {entity_basename} — using placeholder '{geom_identifier}'. "
              f"Provide a matching .geo.json to fix rendering.")
    chosen_animation_key = None
    if primary_animation_key:
        candidate = canonicalize_animation_id(primary_animation_key, namespace, entity_name)
        found = False
        for keys in anim_key_map.values():
            if candidate in keys:
                chosen_animation_key = candidate
                found = True
                break
        if not found:
            for keys in anim_key_map.values():
                for k in keys:
                    if entity_basename.lower() in k.lower() or (geom_tuple and geom_tuple[1].lower() in k.lower()):
                        chosen_animation_key = k
                        found = True
                        break
                if found:
                    break
        if not found and candidate:
            chosen_animation_key = candidate
        if chosen_animation_key:
            chosen_animation_key = canonicalize_animation_id(chosen_animation_key, namespace, entity_name)
    anim_controller_id = None
    if animations:
        anim_controller_id = generate_animation_controller(
            clean_identifier, animations, namespace,
            ai_goals=ai_goals, java_code=java_code
        )
    controller_id = write_render_controller(entity_basename.lower(), namespace.lower(), geom_identifier, uv_anim=None)
    write_rp_entity_json(entity_basename.lower(), namespace.lower(), texture_ref, geom_identifier, chosen_animation_key, controller_id)
    stats["converted_entities_rp"].append(os.path.join(RP_FOLDER, "entity", f"{entity_basename}.entity.json"))
    patch_rp_entity_with_controller(entity_basename.lower(), animations, anim_controller_id, namespace)
    generate_spawn_rules(clean_identifier, java_code, namespace)
    extract_and_generate_particles(java_code, clean_identifier, namespace)
    if "TradeWithPlayerGoal" in ai_goals:
        generate_trading_table(clean_identifier, java_code, namespace)

    generate_entity_script(java_code, clean_identifier.split(":")[-1], clean_identifier, namespace)
def choose_icon_size_for(width: int, height: int) -> int:
    m = min(width, height)
    valid_under = [s for s in VALID_ICON_SIZES if s <= m]
    if valid_under:
        return max(valid_under)
    return VALID_ICON_SIZES[0]
def ensure_and_fix_pack_icon(src_path: str, dest_path: str):
    if not os.path.exists(src_path):
        print(f"[icon] source icon not found: {src_path}")
        return False
    if not PIL_AVAILABLE:
        print(" Pillow (PIL) not installed — pack_icon.png will be copied unmodified. To auto-fix sizing run: pip install pillow")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(src_path, dest_path)
        return False
    try:
        with Image.open(src_path) as im:
            w, h = im.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            right = left + side
            bottom = top + side
            im_cropped = im.crop((left, top, right, bottom))
            target_size = choose_icon_size_for(side, side)
            if (im_cropped.size[0], im_cropped.size[1]) != (target_size, target_size):
                im_resized = im_cropped.resize((target_size, target_size), Image.LANCZOS)
            else:
                im_resized = im_cropped
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            im_resized.save(dest_path, format="PNG")
            print(f"[icon] Wrote pack_icon.png with size {target_size}x{target_size} to {dest_path}")
            return True
    except Exception as e:
        print(f"[icon] Failed to process icon (PIL): {e}. Copying without transform.")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(src_path, dest_path)
        return False
def sanitize_sound_key(k: str) -> str:
    if not k:
        return ""
    s = str(k).lower()
    s = s.replace('-s', '_s')
    s = s.replace('-', '_')
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'[^a-z0-9_\.]', '_', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('._')
    return s
def _normalize_sound_name(name: str) -> str:
    name = name.split(":")[-1]
    for prefix in ("sounds/", "sound/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    if "." in os.path.basename(name):
        name = name.rsplit(".", 1)[0]
    name = sanitize_sound_key(name)
    return f"sound/{name}"
def _sanitize_sound_def(v) -> dict:
    if not isinstance(v, dict):
        return v
    result = dict(v)
    if "sounds" in result and isinstance(result["sounds"], list):
        cleaned = []
        for entry in result["sounds"]:
            if isinstance(entry, str):
                cleaned.append(_normalize_sound_name(entry))
            elif isinstance(entry, dict):
                e = dict(entry)
                if "name" in e and isinstance(e["name"], str):
                    e["name"] = _normalize_sound_name(e["name"])
                cleaned.append(e)
            else:
                cleaned.append(entry)
        result["sounds"] = cleaned
    return result
def generate_sounds_registry(mod_name: str):
    global COLLECTED_SOUND_DEFS
    sounds_dir = os.path.join(RP_FOLDER, "sound")
    if os.path.isdir(sounds_dir):
        for root, _, files in os.walk(sounds_dir):
            for f in files:
                if not f.lower().endswith(".ogg"):
                    continue
                stem = os.path.splitext(f)[0]
                sanitized_key = sanitize_sound_key(stem)
                if sanitized_key not in COLLECTED_SOUND_DEFS:
                    COLLECTED_SOUND_DEFS[sanitized_key] = {"sounds": [{"name": f"sound/{sanitized_key}"}]}
    if COLLECTED_SOUND_DEFS:
        final_defs: Dict[str, dict] = {}
        collisions = 0
        for raw_k, v in COLLECTED_SOUND_DEFS.items():
            new_k = sanitize_sound_key(raw_k)
            v = _sanitize_sound_def(v)
            if new_k in final_defs:
                collisions += 1
                fallback_k = f"{sanitize_sound_key(mod_name)}.{new_k}"
                if fallback_k in final_defs:
                    i = 2
                    while f"{fallback_k}_{i}" in final_defs:
                        i += 1
                    fallback_k = f"{fallback_k}_{i}"
                final_defs[fallback_k] = v
            else:
                final_defs[new_k] = v
        out_path = os.path.join(RP_FOLDER, "sounds", "sound_definitions.json")
        safe_write_json(out_path, {
            "format_version": "1.14.0",
            "sound_definitions": final_defs
        })
        print(f"[sounds] Wrote sound_definitions.json: {len(final_defs)} entries, {collisions} collision(s) resolved")
    else:
        print("[sounds] No sound definitions collected; skipping sound_definitions.json")
    if _ENTITY_SOUND_EVENTS:
        sounds_json: dict = {}
        for entity_id, entry in _ENTITY_SOUND_EVENTS.items():
            outer_key = entity_id if entity_id.startswith("entity.") else f"entity.{entity_id}"
            sounds_json[outer_key] = entry
        out_path = os.path.join(RP_FOLDER, "sounds.json")
        safe_write_json(out_path, sounds_json)
        print(f"[sounds] Wrote sounds.json: {len(sounds_json)} entity sound entr{'y' if len(sounds_json)==1 else 'ies'}")
    else:
        print("[sounds] No entity sound events detected; skipping sounds.json")
JAVA_MOB_EFFECT_MAP = {
    "MOVEMENT_SPEED": "speed", "MOVEMENT_SLOWDOWN": "slowness",
    "DIG_SPEED": "haste", "DIG_SLOWDOWN": "mining_fatigue",
    "DAMAGE_BOOST": "strength", "HEAL": "instant_health",
    "HARM": "instant_damage", "JUMP": "jump_boost",
    "CONFUSION": "nausea", "REGENERATION": "regeneration",
    "DAMAGE_RESISTANCE": "resistance", "FIRE_RESISTANCE": "fire_resistance",
    "WATER_BREATHING": "water_breathing", "INVISIBILITY": "invisibility",
    "BLINDNESS": "blindness", "NIGHT_VISION": "night_vision",
    "HUNGER": "hunger", "WEAKNESS": "weakness", "POISON": "poison",
    "WITHER": "wither", "HEALTH_BOOST": "health_boost",
    "ABSORPTION": "absorption", "SATURATION": "saturation",
    "GLOWING": "glowing", "LEVITATION": "levitation",
    "LUCK": "luck", "UNLUCK": "unluck", "SLOW_FALLING": "slow_falling",
    "CONDUIT_POWER": "conduit_power", "DOLPHINS_GRACE": "dolphins_grace",
    "BAD_OMEN": "bad_omen", "HERO_OF_THE_VILLAGE": "village_hero",
    "DARKNESS": "darkness",
}
def extract_mob_effects_from_java(java_code: str) -> list:
    effects = []
    for m in re.finditer(
        r'new\s+MobEffectInstance\s*\(\s*MobEffects\.([A-Z_]+)\s*,\s*(\d+)\s*(?:,\s*(\d+))?',
        java_code):
        java_name = m.group(1)
        duration_ticks = int(m.group(2))
        amplifier = int(m.group(3)) if m.group(3) else 0
        bedrock_name = JAVA_MOB_EFFECT_MAP.get(java_name)
        if bedrock_name:
            effects.append({
                "effect": bedrock_name,
                "duration": duration_ticks / 20.0,
                "amplifier": amplifier,
                "ambient": False,
                "visible": True
            })
    return effects
JAVA_SOUND_EVENT_MAP = {
    "ENTITY_GENERIC_AMBIENT":      "ambient",
    "ENTITY_GENERIC_DEATH":        "death",
    "ENTITY_GENERIC_HURT":         "hurt",
    "ENTITY_GENERIC_STEP":         "step",
    "ENTITY_GENERIC_SPLASH":       "splash",
    "ENTITY_GENERIC_SWIM":         "swim",
    "ENTITY_GENERIC_BIG_FALL":     "fall.big",
    "ENTITY_GENERIC_SMALL_FALL":   "fall.small",
    "ENTITY_GENERIC_DRINK":        "drink",
    "ENTITY_GENERIC_EAT":          "eat",
    "ENTITY_GENERIC_EXPLODE":      "explode",
    "ENTITY_GENERIC_ATTACK":       "attack",
    "ENTITY_ZOMBIE_AMBIENT":       "ambient",
    "ENTITY_ZOMBIE_DEATH":         "death",
    "ENTITY_ZOMBIE_HURT":          "hurt",
    "ENTITY_SKELETON_AMBIENT":     "ambient",
    "ENTITY_SKELETON_DEATH":       "death",
    "ENTITY_SKELETON_HURT":        "hurt",
    "ENTITY_CREEPER_PRIMED":       "ambient",
    "ENTITY_WOLF_AMBIENT":         "ambient",
    "ENTITY_WOLF_DEATH":           "death",
    "ENTITY_WOLF_HURT":            "hurt",
    "ENTITY_CAT_AMBIENT":          "ambient",
    "ENTITY_PLAYER_ATTACK_STRONG": "attack",
    "ENTITY_PLAYER_HURT":          "hurt",
    "ENTITY_PLAYER_DEATH":         "death",
    "ENTITY_ENDERMAN_AMBIENT":     "ambient",
    "ENTITY_ENDERMAN_DEATH":       "death",
    "ENTITY_ENDERMAN_HURT":        "hurt",
    "ENTITY_ENDERMAN_STARE":       "ambient.stare",
    "ENTITY_WARDEN_AMBIENT":       "ambient",
    "ENTITY_WARDEN_DEATH":         "death",
    "ENTITY_WARDEN_HURT":          "hurt",
    "ENTITY_WARDEN_ROAR":          "roar",
}
JAVA_SOUND_METHOD_MAP = {
    "getAmbientSound":  "ambient",
    "ambientSound":     "ambient",
    "getDeathSound":    "death",
    "deathSound":       "death",
    "getHurtSound":     "hurt",
    "hurtSound":        "hurt",
    "getStepSound":     "step",
    "stepSound":        "step",
    "getSwimSound":     "swim",
    "swimSound":        "swim",
    "getSplashSound":   "splash",
    "splashSound":      "splash",
}
def _best_sound_key(raw_id: str, namespace: str) -> str:
    raw_id = raw_id.strip().strip('"').strip("'")
    if ":" in raw_id:
        raw_id = raw_id.split(":", 1)[1]
    return sanitize_sound_key(raw_id)
def extract_entity_sounds_from_java(java_code: str, entity_name: str, namespace: str) -> dict:
    sounds = {}
    for method, slot in JAVA_SOUND_METHOD_MAP.items():
        pat = rf'{method}\s*\([^)]*\)\s*\{{[^}}]*?(?:return\s+)?(?:SoundEvents\.|ModSounds\.|Sounds\.)([A-Z0-9_]+)'
        m = re.search(pat, java_code, re.DOTALL)
        if m and slot not in sounds:
            java_const = m.group(1)
            bedrock_slot = JAVA_SOUND_EVENT_MAP.get(java_const)
            if bedrock_slot:
                sounds[slot] = f"{namespace}.{entity_name}.{slot}"
            else:
                sounds[slot] = sanitize_sound_key(java_const.lower())
    for method, slot in JAVA_SOUND_METHOD_MAP.items():
        if slot in sounds:
            continue
        pat = rf'{method}\s*\([^)]*\)\s*\{{[^}}]*?return\s+([A-Za-z_][A-Za-z0-9_.]*(?:\.get\(\))?)'
        m = re.search(pat, java_code, re.DOTALL)
        if m:
            ref = m.group(1).rstrip(")").rstrip("(").rstrip(".get")
            ref_lower = sanitize_sound_key(ref.split(".")[-1])
            if len(ref_lower) > 2 and ref_lower not in ("null", "super", "this"):
                sounds[slot] = f"{namespace}.{ref_lower}"
    PLAY_SLOT_HINTS = {
        "ambient": ("ambient", "idle", "random"),
        "hurt":    ("hurt", "pain", "damage"),
        "death":   ("death", "die"),
        "attack":  ("attack", "strike", "hit"),
        "step":    ("step", "footstep", "walk"),
    }
    for m in re.finditer(
        r'playSound\s*\([^,)]*,\s*(?:SoundEvents\.|ModSounds\.|Sounds\.)([A-Z0-9_]+)',
        java_code
    ):
        java_const = m.group(1)
        for slot, hints in PLAY_SLOT_HINTS.items():
            if slot in sounds:
                continue
            if any(h in java_const.lower() for h in hints):
                sounds[slot] = f"{namespace}.{entity_name}.{slot}"
                break
    for m in re.finditer(
        r'new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
        java_code
    ):
        sound_path = m.group(2).lower()
        for slot in ("ambient", "death", "hurt", "step", "attack", "swim", "splash"):
            if slot in sounds:
                continue
            if slot in sound_path:
                key = sanitize_sound_key(f"{m.group(1)}.{sound_path}")
                sounds[slot] = key
                break
    for m in re.finditer(
        r'["\']([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,})["\']',
        java_code
    ):
        path = m.group(1)
        parts = path.split(".")
        if len(parts) < 2:
            continue
        for slot in ("ambient", "death", "hurt", "step", "attack", "swim", "splash"):
            if slot in sounds:
                continue
            if parts[-1] == slot or (len(parts) >= 2 and parts[-2] == slot):
                sounds[slot] = sanitize_sound_key(path)
                break
    return sounds
def apply_entity_sounds(bedrock_entity: dict, sounds: dict, namespace: str,
                        entity_name: str):
    if not sounds:
        return
    components = bedrock_entity["minecraft:entity"]["components"]
    entity_id = bedrock_entity["minecraft:entity"]["description"]["identifier"]
    if "ambient" in sounds:
        components["minecraft:ambient_sound_interval"] = {
            "value": 8.0,
            "range": 4.0,
            "event_name": sounds["ambient"]
        }
    SLOT_TO_BEDROCK_EVENT = {
        "ambient": "ambient",
        "hurt":    "hurt",
        "death":   "death",
        "step":    "step",
        "attack":  "attack",
        "swim":    "swim",
        "splash":  "splash",
    }
    events_block = {}
    for slot, event_key in SLOT_TO_BEDROCK_EVENT.items():
        if slot in sounds:
            events_block[event_key] = sounds[slot]
    if events_block:
        _ENTITY_SOUND_EVENTS[entity_id] = {
            "events": events_block,
            "pitch": [0.8, 1.2],
            "volume": 1.0
        }
    for slot, sound_key in sounds.items():
        if sound_key not in COLLECTED_SOUND_DEFS:
            file_stem = sound_key.replace(".", "_")
            file_path = f"sound/{file_stem}"
            COLLECTED_SOUND_DEFS[sound_key] = {
                "sounds": [{"name": file_path}],
                "__stub__": True
            }
            print(f"  [sounds] Stub entry created: {sound_key} -> {file_path}")
JAVA_SLOT_TO_BEDROCK = {
    "HEAD": "slot.armor.head",
    "CHEST": "slot.armor.chest",
    "LEGS": "slot.armor.legs",
    "FEET": "slot.armor.feet",
    "MAINHAND": "slot.weapon.mainhand",
    "OFFHAND": "slot.weapon.offhand",
}
def extract_equipment_from_java(java_code: str, namespace: str) -> Optional[dict]:
    equipment = {}
    for m in re.finditer(
        r'(?:setItemSlot|setEquipment|set)\s*\(\s*EquipmentSlot\.([A-Z]+)\s*,\s*new\s+ItemStack\s*\(\s*(?:Items\.)?([A-Za-z_]+)',
        java_code):
        slot = JAVA_SLOT_TO_BEDROCK.get(m.group(1))
        item = sanitize_identifier(m.group(2).lower())
        if slot:
            if not item.startswith("minecraft:"):
                item = f"minecraft:{item}"
            equipment[slot] = {"item": item, "drop_chance": 0.085}
    if not equipment:
        return None
    return {"table": f"loot_tables/equipment/{namespace}_equipment.json", "slot_drop_chance": list(equipment.values())}
def generate_entity_events(bedrock_entity: dict, ai_goals: list, java_code: str,
                           namespace: str, entity_id: str, attributes: dict):
    components = bedrock_entity["minecraft:entity"]["components"]
    events = bedrock_entity["minecraft:entity"]["events"]
    component_groups = {}
    ns_prefix = entity_id.split(":")[0] if ":" in entity_id else namespace
    taming_goals = ("SitWhenOrderedToGoal", "FollowOwnerGoal", "OwnerHurtByTargetGoal", "OwnerHurtTargetGoal")
    if any(g in ai_goals for g in taming_goals):
        component_groups[f"{ns_prefix}:tamed"] = {
            "minecraft:is_tamed": {},
            "minecraft:behavior.follow_owner": {
                "priority": 7,
                "speed_multiplier": 1.2,
                "start_distance": 10.0,
                "stop_distance": 2.0
            }
        }
        component_groups[f"{ns_prefix}:wild"] = {
            "minecraft:behavior.nearest_attackable_target": components.get(
                "minecraft:behavior.nearest_attackable_target",
                {"priority": 1, "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": 16}]}
            )
        }
        events["minecraft:on_tame"] = {
            "add": {"component_groups": [f"{ns_prefix}:tamed"]},
            "remove": {"component_groups": [f"{ns_prefix}:wild"]}
        }
        events["minecraft:on_untame"] = {
            "add": {"component_groups": [f"{ns_prefix}:wild"]},
            "remove": {"component_groups": [f"{ns_prefix}:tamed"]}
        }
    if "ResetAngerGoal" in ai_goals or "HurtByTargetGoal" in ai_goals:
        component_groups[f"{ns_prefix}:angry"] = {
            "minecraft:behavior.nearest_attackable_target": {
                "priority": 1,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": int(attributes.get("follow_range", 16))}],
                "must_see": False,
                "reselect_targets": True
            }
        }
        component_groups[f"{ns_prefix}:calm"] = {
            "minecraft:behavior.random_stroll": {"priority": 8, "speed_multiplier": attributes.get("movement_speed", 0.3)}
        }
        events["minecraft:on_anger"] = {
            "add": {"component_groups": [f"{ns_prefix}:angry"]},
            "remove": {"component_groups": [f"{ns_prefix}:calm"]}
        }
        events["minecraft:on_calm"] = {
            "add": {"component_groups": [f"{ns_prefix}:calm"]},
            "remove": {"component_groups": [f"{ns_prefix}:angry"]}
        }
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    loot_path = f"loot_tables/entities/{safe_name}.json"
    if os.path.exists(os.path.join(BP_FOLDER, loot_path)):
        components["minecraft:loot"] = {"table": loot_path}
    component_groups[f"{ns_prefix}:dead"] = {"minecraft:despawn": {}}
    events["minecraft:on_death"] = {
        "add": {"component_groups": [f"{ns_prefix}:dead"]}
    }
    mob_effects = extract_mob_effects_from_java(java_code)
    if mob_effects:
        component_groups[f"{ns_prefix}:hurt_effects"] = {
            "minecraft:mob_effect": {"effect": mob_effects[0]["effect"],
                                     "duration": mob_effects[0]["duration"],
                                     "amplifier": mob_effects[0]["amplifier"]}
        }
        events["minecraft:on_hurt"] = {
            "add": {"component_groups": [f"{ns_prefix}:hurt_effects"]}
        }
        if re.search(r'addEffect|hurt\(.+MobEffects', java_code, re.I):
            components["minecraft:attack_effect"] = {
                "effect": mob_effects[0]["effect"],
                "duration": mob_effects[0]["duration"],
                "amplifier": mob_effects[0]["amplifier"]
            }
    entity_name_short = entity_id.split(":")[-1] if ":" in entity_id else entity_id
    detected_sounds = extract_entity_sounds_from_java(java_code, entity_name_short, namespace)
    apply_entity_sounds(bedrock_entity, detected_sounds, namespace, entity_name_short)
    equip = extract_equipment_from_java(java_code, namespace)
    if equip:
        components["minecraft:equipment"] = equip
    kr = attributes.get("knockback_resistance", 0.0)
    if kr > 0:
        components["minecraft:knockback_resistance"] = {"value": min(1.0, kr)}
    if component_groups:
        bedrock_entity["minecraft:entity"]["component_groups"] = component_groups
JAVA_BIOME_TO_BEDROCK = {
    "plains": "plains", "desert": "desert", "forest": "forest",
    "taiga": "taiga", "swamp": "swamp", "jungle": "jungle",
    "savanna": "savanna", "badlands": "mesa", "snowy": "frozen",
    "mountains": "extreme_hills", "birch_forest": "birch",
    "dark_forest": "roofed_forest", "mushroom": "mushroom_island",
    "beach": "beach", "ocean": "ocean", "deep_ocean": "deep_ocean",
    "river": "river", "nether": "nether", "end": "the_end",
    "basalt_deltas": "basalt_deltas", "crimson_forest": "crimson_forest",
    "warped_forest": "warped_forest", "soul_sand_valley": "soulsand_valley",
    "meadow": "meadow", "grove": "grove", "snowy_slopes": "snowy_slopes",
    "jagged_peaks": "jagged_peaks", "frozen_peaks": "frozen_peaks",
    "stony_peaks": "stony_peaks", "lush_caves": "lush_caves",
    "dripstone_caves": "dripstone_caves", "deep_dark": "deep_dark",
    "mangrove_swamp": "mangrove_swamp", "cherry_grove": "cherry_grove",
    "overworld": "overworld", "underground": "underground",
}
def extract_spawn_data_from_java(java_code: str) -> dict:
    data = {
        "biomes": [],
        "min_light": 0,
        "max_light": 15,
        "min_count": 1,
        "max_count": 4,
        "weight": 10,
        "surface": True,
        "underground": False,
    }
    biome_matches = re.findall(
        r'(?:BiomeDictionary|BiomeCategory|Tags\.Biomes|BIOMES?)[\.\s]+([A-Z_a-z]+)',
        java_code)
    biome_matches += re.findall(r'BiomeTags\.(?:IS_)?([A-Z_]+)', java_code)
    biome_matches += re.findall(r'TagKey[^"]*["\']([a-z_:]+)["\']', java_code)
    for b in biome_matches:
        bl = b.lower()
        for k, v in JAVA_BIOME_TO_BEDROCK.items():
            if k in bl or bl in k:
                if v not in data["biomes"]:
                    data["biomes"].append(v)
    if not data["biomes"]:
        if re.search(r'NETHER|nether', java_code, re.I): data["biomes"] = ["nether"]
        elif re.search(r'THE_END|the_end', java_code, re.I): data["biomes"] = ["the_end"]
        else: data["biomes"] = ["overworld"]
    if re.search(r'MobCategory\.NETHER|DimensionType\.NETHER', java_code): data["biomes"] = ["nether"]
    if re.search(r'MobCategory\.END|DimensionType\.END', java_code): data["biomes"] = ["the_end"]
    for wpat in [r'SpawnEntry[^(]*\(\s*(\d+)', r'weight\s*[=:]\s*(\d+)', r'\.weight\s*\(\s*(\d+)\s*\)']:
        m = re.search(wpat, java_code, re.I)
        if m:
            data["weight"] = int(m.group(1)); break
    m = re.search(r'SpawnEntry[^(]*\([^,]+,\s*(\d+)\s*,\s*(\d+)', java_code)
    if m:
        data["min_count"] = int(m.group(1))
        data["max_count"] = int(m.group(2))
    m = re.search(r'(?:light|lightLevel|maxLight)\s*[=<>]+\s*(\d+)', java_code, re.I)
    if m:
        data["max_light"] = int(m.group(1))
    if re.search(r'IN_WATER|water', java_code, re.I):
        data["surface"] = False
    if re.search(r'UNDERGROUND|underground|cave|Cave', java_code):
        data["underground"] = True
        data["surface"] = False
    return data
def generate_spawn_rules(entity_id: str, java_code: str, namespace: str):
    spawn_data = extract_spawn_data_from_java(java_code)
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    out_path = os.path.join(BP_FOLDER, "spawn_rules", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    conditions = []
    for biome in spawn_data["biomes"]:
        condition = {
            "minecraft:spawns_on_surface": {} if spawn_data["surface"] else None,
            "minecraft:spawns_underground": {} if spawn_data["underground"] else None,
            "minecraft:brightness_filter": {
                "min": spawn_data["min_light"],
                "max": spawn_data["max_light"],
                "adjust_for_weather": False
            },
            "minecraft:biome_filter": {"test": "has_biome_tag", "operator": "==", "value": biome},
            "minecraft:herd": {
                "min_size": spawn_data["min_count"],
                "max_size": spawn_data["max_count"]
            },
            "minecraft:weight": {"default": spawn_data["weight"]}
        }
        condition = {k: v for k, v in condition.items() if v is not None}
        conditions.append(condition)
    doc = {
        "format_version": "1.12.0",
        "minecraft:spawn_rules": {
            "description": {"identifier": entity_id, "population_control": "monster"},
            "conditions": conditions
        }
    }
    safe_write_json(out_path, doc)
    print(f"[spawn_rules] Wrote {out_path}")
JAVA_LOOT_ITEM_MAP = {
    "minecraft:bone": "minecraft:bone",
    "minecraft:rotten_flesh": "minecraft:rotten_flesh",
    "minecraft:string": "minecraft:string",
    "minecraft:arrow": "minecraft:arrow",
    "minecraft:blaze_rod": "minecraft:blaze_rod",
    "minecraft:gunpowder": "minecraft:gunpowder",
    "minecraft:ender_pearl": "minecraft:ender_pearl",
    "minecraft:leather": "minecraft:leather",
    "minecraft:feather": "minecraft:feather",
    "minecraft:experience_bottle": "minecraft:experience_bottle",
    "minecraft:coal": "minecraft:coal",
    "minecraft:iron_ingot": "minecraft:iron_ingot",
    "minecraft:gold_ingot": "minecraft:gold_ingot",
    "minecraft:diamond": "minecraft:diamond",
    "minecraft:emerald": "minecraft:emerald",
    "minecraft:beef": "minecraft:beef",
    "minecraft:cooked_beef": "minecraft:cooked_beef",
    "minecraft:porkchop": "minecraft:porkchop",
    "minecraft:cooked_porkchop": "minecraft:cooked_porkchop",
    "minecraft:chicken": "minecraft:chicken",
    "minecraft:cooked_chicken": "minecraft:cooked_chicken",
    "minecraft:mutton": "minecraft:mutton",
    "minecraft:cooked_mutton": "minecraft:cooked_mutton",
}
def convert_java_loot_table(java_loot: dict, namespace: str) -> dict:
    pools = []
    for pool in java_loot.get("pools", []):
        rolls = pool.get("rolls", 1)
        if isinstance(rolls, dict):
            roll_val = {"min": rolls.get("min", 1), "max": rolls.get("max", 1)}
        else:
            roll_val = int(rolls)
        entries = []
        for entry in pool.get("entries", []):
            etype = entry.get("type", "")
            if "empty" in etype:
                continue
            if "item" in etype:
                item_name = entry.get("name", "")
                if ":" in item_name:
                    ns, item = item_name.split(":", 1)
                    if ns != "minecraft":
                        item_name = f"{namespace}:{sanitize_identifier(item)}"
                    else:
                        item_name = JAVA_LOOT_ITEM_MAP.get(item_name, item_name)
                bedrock_entry = {
                    "type": "item",
                    "name": item_name,
                    "weight": entry.get("weight", 1)
                }
                functions = []
                for func in entry.get("functions", []):
                    fname = func.get("function", "")
                    if "count" in fname or "set_count" in fname:
                        count = func.get("count", 1)
                        if isinstance(count, dict):
                            functions.append({
                                "function": "set_count",
                                "count": {"min": count.get("min", 1), "max": count.get("max", 1)}
                            })
                        else:
                            functions.append({"function": "set_count", "count": int(count)})
                    elif "looting" in fname or "enchant_with_levels" in fname:
                        functions.append({
                            "function": "looting_enchant",
                            "count": {"min": 0, "max": 1}
                        })
                if functions:
                    bedrock_entry["functions"] = functions
                entries.append(bedrock_entry)
            elif "loot_table" in etype or "alternatives" in etype:
                entries.append({"type": "item", "name": "minecraft:air", "weight": 1})
        if entries:
            pools.append({"rolls": roll_val, "entries": entries})
    return {"pools": pools}
def process_loot_tables_from_jar(jar_path: str, namespace: str):
    out_base = os.path.join(BP_FOLDER, "loot_tables", "entities")
    os.makedirs(out_base, exist_ok=True)
    count = 0
    with zipfile.ZipFile(jar_path, "r") as jar:
        for name in jar.namelist():
            lower = name.lower()
            if "loot_table" not in lower and "loot_tables" not in lower:
                continue
            if not lower.endswith(".json"):
                continue
            try:
                with jar.open(name) as f:
                    data = json.loads(f.read().decode("utf-8"))
                bedrock = convert_java_loot_table(data, namespace)
                if not bedrock.get("pools"):
                    continue
                fname = sanitize_filename_keep_ext(os.path.basename(name))
                out_path = os.path.join(out_base, fname)
                safe_write_json(out_path, bedrock)
                count += 1
            except Exception as e:
                print(f"[loot] Failed to convert {name}: {e}")
    print(f"[loot] Converted {count} loot tables -> {out_base}")
