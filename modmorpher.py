from __future__ import annotations

Tool_Version = "1.4.1.1"

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
def generate_entity_script(java_code: str, entity_name: str, entity_id: str, namespace: str):
    symbol_table = JavaSymbolTable()
    symbol_table.scan_java_file(java_code)


    tick_method = detect_tick_method(java_code)
    if not tick_method:
        return

    tick_logic = tick_method[1]


    if not JAVALANG_AVAILABLE:
        return

    try:
        tree = javalang.parse.parse(f"class Dummy {{ {tick_logic} }}")
    except:
        return

    method_body = None
    for cls in tree.types:
        for method in cls.methods:
            if method.name == 'tick':
                method_body = method.body
                break

    if not method_body:
        return

    js_lines = []
    for stmt in method_body:
        translated = translate_statement(stmt, 'entity', namespace, symbol_table)
        js_lines.extend(translated)

    if not js_lines:
        return


    script_content = [
        'import { world, system } from "@minecraft/server";',
        '',
        f'// Entity script for {entity_id}',
        f'world.afterEvents.entitySpawn.subscribe((event) => {{',
        f'    if (event.entity.typeId === "{entity_id}") {{',
        f'        event.entity.addTag("mod:needs_tick");',
        f'    }}',
        f'}});',
        '',
        '// Tick logic',
        'const tick_handlers = {};',
        f'tick_handlers["{entity_id}"] = (entity) => {{',
    ]
    script_content.extend(js_lines)
    script_content.extend([
        '};',
        '',
        '// Register with central tick registry',
        'import("./main.js").then(() => {',
        '    if (typeof tick_registry !== "undefined") {',
        f'        tick_registry.handlers["{entity_id}"] = tick_handlers["{entity_id}"];',
        '    }',
        '});'
    ])

    out_path = os.path.join(BP_FOLDER, "scripts", f"{entity_name}.js")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(script_content))

    print(f"[script] Generated entity script: {out_path}")
def generate_trading_table(entity_id: str, java_code: str, namespace: str):
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    out_path = os.path.join(BP_FOLDER, "trading", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    trade_items = re.findall(
        r'new\s+MerchantOffer[^;]+new\s+ItemStack\(([^)]+)\)', java_code)
    tiers = []
    if trade_items:
        trades = []
        for item_ref in trade_items[:6]:
            item_name = sanitize_identifier(item_ref.split(".")[-1].split(",")[0].lower())
            trades.append({
                "wants": [{"item": f"minecraft:emerald", "quantity": 1}],
                "gives": [{"item": f"{namespace}:{item_name}", "quantity": 1}],
                "trader_exp": 1, "max_uses": 12, "reward_exp": True
            })
        tiers.append({"total_exp_required": 0, "groups": [{"num_to_select": len(trades), "trades": trades}]})
    else:
        tiers.append({
            "total_exp_required": 0,
            "groups": [{"num_to_select": 1, "trades": [
                {"wants": [{"item": "minecraft:emerald", "quantity": 1}],
                 "gives": [{"item": f"{namespace}:item", "quantity": 1}],
                 "trader_exp": 1, "max_uses": 12, "reward_exp": True}
            ]}]
        })
    doc = {"tiers": tiers}
    safe_write_json(out_path, doc)
    print(f"[trading] Wrote {out_path}")
JAVA_TAG_TO_BEDROCK_GROUP = {
    "forge:ores": "ore",
    "forge:ingots": "ingot",
    "forge:gems": "gem",
    "forge:dusts": "dust",
    "forge:nuggets": "nugget",
    "forge:rods": "stick",
    "forge:plates": "plate",
    "forge:tools": "tool",
    "forge:tools/swords": "weapon",
    "forge:tools/axes": "tool",
    "forge:tools/pickaxes": "tool",
    "forge:tools/shovels": "tool",
    "forge:tools/hoes": "tool",
    "forge:weapons": "weapon",
    "forge:armor": "armor",
    "forge:armors": "armor",
    "forge:food": "food",
    "forge:seeds": "seeds",
    "forge:crops": "crop",
    "forge:bones": "misc",
    "forge:string": "misc",
    "forge:feathers": "misc",
    "forge:storage_blocks": "misc",
    "forge:raw_materials": "misc",
    "neoforge:ores": "ore",
    "neoforge:ingots": "ingot",
    "neoforge:gems": "gem",
    "c:ores": "ore",
    "c:ingots": "ingot",
    "c:gems": "gem",
    "c:dusts": "dust",
    "c:nuggets": "nugget",
    "c:foods": "food",
    "c:tools": "tool",
    "c:weapons": "weapon",
    "c:armors": "armor",
    "minecraft:logs": "log",
    "minecraft:logs_that_burn": "log",
    "minecraft:planks": "planks",
    "minecraft:slabs": "slab",
    "minecraft:stairs": "stair",
    "minecraft:doors": "door",
    "minecraft:trapdoors": "door",
    "minecraft:leaves": "leaves",
    "minecraft:saplings": "sapling",
    "minecraft:flowers": "flower",
    "minecraft:small_flowers": "flower",
    "minecraft:tall_flowers": "flower",
    "minecraft:wool": "wool",
    "minecraft:swords": "weapon",
    "minecraft:axes": "tool",
    "minecraft:pickaxes": "tool",
    "minecraft:shovels": "tool",
    "minecraft:hoes": "tool",
    "minecraft:helmets": "armor",
    "minecraft:chestplates": "armor",
    "minecraft:leggings": "armor",
    "minecraft:boots": "armor",
    "minecraft:coals": "misc",
    "minecraft:arrows": "misc",
    "minecraft:beds": "misc",
    "minecraft:banners": "misc",
    "minecraft:music_discs": "misc",
    "minecraft:fishes": "food",
    "minecraft:meat": "food",
}
def extract_item_tags_from_jar(jar_path: str, namespace: str):
    out_dir = os.path.join(BP_FOLDER, "item_catalog")
    os.makedirs(out_dir, exist_ok=True)
    catalog = {"format_version": "1.21.0", "minecraft:item_catalog": {"description": {"identifier": f"{namespace}:catalog"}, "groups": []}}
    groups: Dict[str, list] = {}
    with zipfile.ZipFile(jar_path, "r") as jar:
        for name in jar.namelist():
            lower = name.lower()
            if "/tags/items/" not in lower or not lower.endswith(".json"):
                continue
            try:
                with jar.open(name) as f:
                    data = json.loads(f.read().decode("utf-8"))
                tag_name = os.path.splitext(os.path.basename(name))[0]
                group = None
                for java_tag, bedrock_group in JAVA_TAG_TO_BEDROCK_GROUP.items():
                    if tag_name in java_tag or java_tag.split(":")[-1] in tag_name:
                        group = bedrock_group
                        break
                if not group:
                    group = sanitize_identifier(tag_name)
                if group not in groups:
                    groups[group] = []
                for value in data.get("values", []):
                    if isinstance(value, str) and ":" in value:
                        ns, item = value.split(":", 1)
                        if ns != "minecraft":
                            item_id = f"{namespace}:{sanitize_identifier(item)}"
                        else:
                            item_id = value
                        if item_id not in groups[group]:
                            groups[group].append(item_id)
            except Exception as e:
                print(f"[tags] Failed to parse {name}: {e}")
    for group_name, items in groups.items():
        if items:
            catalog["minecraft:item_catalog"]["groups"].append({
                "group_name": group_name,
                "items": items
            })
    if catalog["minecraft:item_catalog"]["groups"]:
        out_path = os.path.join(out_dir, f"{namespace}_catalog.json")
        safe_write_json(out_path, catalog)


def run_class_decompiler(jar_file, output_dir):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    lib_jar = os.path.join(script_dir, "tools", "ClassDecompiler.jar")

    if not os.path.exists(lib_jar):
        print(f"Error: ClassDecompiler.jar not found at {lib_jar}")
        return None

    try:
        with zipfile.ZipFile(lib_jar, 'r') as z:
            internal_path = next(
                (name for name in z.namelist() if "vineflower.jar" in name.lower()), 
                None
            )
            if internal_path:
                z.extract(internal_path, script_dir)
                extracted_engine = os.path.join(script_dir, internal_path)
            else:
                print("Vineflower jar not found in ClassDecompiler.jar")
                return None

        subprocess.run(
            ["java", "-jar", os.path.abspath(lib_jar), 
             os.path.abspath(jar_file), os.path.abspath(output_dir)],
            cwd=script_dir,
            check=True
        )
        return extracted_engine

    except Exception as e:
        print(f"Decompilation failure: {e}")
        return None


def main():
    target_jar = next(
        (f for f in os.listdir(".") if f.endswith(".jar")), 
        None
    )

    if not target_jar:
        print("No target jar file found.")
        return

    modmorpher_input_folder = f"src_{os.path.splitext(target_jar)[0]}"

    extracted_engine = run_class_decompiler(target_jar, modmorpher_input_folder)

    if extracted_engine:
        print(f"Decompilation successful. Preparing environment for ModMorpher...")

        if os.path.exists(extracted_engine):
            os.remove(extracted_engine)

        print("Running modmorpher pipeline...")
        run_pipeline()

        print("Pipeline finished.")
    else:
        print("Pipeline aborted due to decompiler errors.")
def find_best_texture_match(safe_name: str, subfolder: str) -> str:
    tex_dir = os.path.join(RP_FOLDER, "textures", subfolder)
    if not os.path.isdir(tex_dir):
        return safe_name
    candidates = []
    for fname in os.listdir(tex_dir):
        if fname.lower().endswith(".png"):
            candidates.append(os.path.splitext(fname)[0])
    if not candidates:
        return safe_name
    if safe_name in candidates:
        return safe_name
    base = safe_name
    for suffix in ("block", "item", "entity", "mob", "_block", "_item", "_entity", "_mob"):
        if base.endswith(suffix):
            base = base[:-len(suffix)].strip("_")
            break
    if base in candidates:
        return base
    name_tokens = set(safe_name.split("_"))
    base_tokens = set(base.split("_"))
    best = safe_name
    best_score = 0
    for c in candidates:
        c_tokens = set(c.split("_"))
        score = len(c_tokens & name_tokens) + len(c_tokens & base_tokens)
        if score > best_score:
            best_score = score
            best = c
    if best_score > 0:
        return best
    return safe_name
JAVA_BLOCK_MATERIAL_MAP = {
    "WOOD": "wood", "STONE": "stone", "METAL": "metal", "SAND": "sand",
    "GLASS": "glass", "CLOTH": "wool", "PLANT": "plant", "DIRT": "dirt",
    "GRASS": "dirt", "ICE": "ice", "LEAVES": "leaves", "WEB": "web",
    "SPONGE": "sponge", "WATER": "water", "LAVA": "lava",
    "FIRE": "decoration", "DECORATION": "decoration",
}
def convert_java_block_full(java_code: str, java_path: str, namespace: str):
    cls = extract_class_name(java_code) or os.path.splitext(os.path.basename(java_path))[0]
    safe_name = sanitize_identifier(cls)
    block_id = f"{namespace}:{safe_name}"
    props = extract_block_properties_from_java(java_code)
    mat_raw = re.search(r'Material\.([A-Z_]+)', java_code)
    material_key = mat_raw.group(1) if mat_raw else ""
    material = JAVA_BLOCK_MATERIAL_MAP.get(material_key, "stone")
    hardness = props.get("destroy_time") if props.get("destroy_time") is not None else 2.0
    resistance = props.get("explosion_resistance") if props.get("explosion_resistance") is not None else hardness * 3.0
    light_emission = props.get("light_emission", 0)
    friction = props.get("friction", 0.6)
    is_opaque = props.get("is_opaque", True)
    render_method = "opaque" if is_opaque else "alpha_test"
    tex_match = find_best_texture_match(safe_name, "blocks")
    doc = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:block": {
            "description": {
                "identifier": block_id,
                "menu_category": {"category": "construction"}
            },
            "components": {
                "minecraft:material_instances": {
                    "*": {"texture": tex_match, "render_method": render_method}
                },
                "minecraft:destructible_by_mining": {"seconds_to_destroy": hardness},
                "minecraft:destructible_by_explosion": {"explosion_resistance": resistance},
                "minecraft:friction": friction,
                "minecraft:light_emission": light_emission,
            }
        }
    }
    comps = doc["minecraft:block"]["components"]
    geo_dir = os.path.join(RP_FOLDER, "geometry")
    geo_candidates = [
        safe_name + ".geo.json",
        safe_name + ".json",
    ]
    has_geo = any(os.path.exists(os.path.join(geo_dir, c)) for c in geo_candidates)
    if has_geo:
        comps["minecraft:geometry"] = f"geometry.{safe_name}"
    if "log" in safe_name or "pillar" in safe_name.lower():
        comps["minecraft:geometry"] = "geometry.log"
    states = {}
    permutations = []
    if re.search(r'BlockStateProperties\.FACING|DirectionProperty', java_code, re.I):
        states["facing"] = ["north", "south", "east", "west", "up", "down"]
        rot_map = {"north": 0, "south": 180, "east": 90, "west": 270}
        for d, rot in rot_map.items():
            permutations.append({
                "condition": f'query.block_property("{namespace}:facing") == "{d}"',
                "components": {"minecraft:transformation": {"rotation": [0, rot, 0]}}
            })
    if re.search(r'BlockStateProperties\.POWERED|BooleanProperty.*power', java_code, re.I):
        states["powered"] = [False, True]
        permutations.append({
            "condition": f'query.block_property("{namespace}:powered") == true',
            "components": {"minecraft:light_emission": min(15, light_emission + 8)}
        })
    if re.search(r'BlockStateProperties\.WATERLOGGED', java_code, re.I):
        states["waterlogged"] = [False, True]
    if re.search(r'BlockStateProperties\.OPEN|BooleanProperty.*open', java_code, re.I):
        states["open"] = [False, True]
    if re.search(r'BlockStateProperties\.LIT|BooleanProperty.*lit', java_code, re.I):
        states["lit"] = [False, True]
        permutations.append({
            "condition": f'query.block_property("{namespace}:lit") == true',
            "components": {"minecraft:light_emission": 15}
        })
    if re.search(r'IntegerProperty.*age|BlockStateProperties\.AGE', java_code, re.I):
        m_age = re.search(r'IntegerProperty\.create\s*\([^,]+,\s*\d+,\s*(\d+)', java_code)
        max_age = int(m_age.group(1)) if m_age else 7
        states["age"] = list(range(max_age + 1))
    if re.search(r'HORIZONTAL_FACING|HorizontalDirectionalBlock', java_code, re.I):
        if "facing" not in states:
            states["facing"] = ["north", "south", "east", "west"]
    if states:
        doc["minecraft:block"]["description"]["states"] = {f"{namespace}:{k}": v for k, v in states.items()}
    if permutations:
        doc["minecraft:block"]["permutations"] = permutations
    generate_block_script(java_code, safe_name, block_id, namespace)
    _finish_block_json(doc, safe_name)
_BLOCK_EVENT_METHOD_MAP = {
    "use":             ("afterEvents", "playerInteractWithBlock", "event.player"),
    "attack":          ("afterEvents", "playerInteractWithBlock", "event.player"),
    "stepOn":          ("afterEvents", "entityStepOnBlock",       "event.entity"),
    "fallOn":          ("afterEvents", "entityFallOnBlock",       "event.entity"),
    "entityInside":    ("afterEvents", "entityEnterBlock",        "event.entity"),
    "neighborChanged": ("afterEvents", "playerPlaceBlock",        "event.player"),
    "onPlace":         ("afterEvents", "playerPlaceBlock",        "event.player"),
    "onRemove":        ("afterEvents", "playerBreakBlock",        "event.player"),
    "playerDestroy":   ("afterEvents", "playerBreakBlock",        "event.player"),
}

_BLOCK_TICK_METHODS = ["randomTick", "tick", "animateTick"]

def generate_block_script(java_code: str, safe_name: str, block_id: str, namespace: str) -> bool:
    found_methods = []
    for method_name, (phase, bedrock_event, entity_ref) in _BLOCK_EVENT_METHOD_MAP.items():
        body = _extract_method_body(java_code, method_name)
        if body:
            found_methods.append((method_name, phase, bedrock_event, entity_ref, body))


    tick_bodies = []
    for method_name in _BLOCK_TICK_METHODS:
        body = _extract_method_body(java_code, method_name)
        if body:
            tick_bodies.append((method_name, body))


    has_be_ticker = bool(re.search(
        r'getTicker\s*\(|BlockEntityTicker\s*<|createTickerHelper\s*\(',
        java_code
    ))
    if has_be_ticker and not tick_bodies:

        tick_bodies.append(("blockEntityTick", ""))


    if re.search(r'AbstractContainerMenu|MenuType|createMenu\s*\(|getMenuType\s*\(', java_code):
        _PORTING_NOTES.append(
            f"[block] {safe_name}: uses a ContainerMenu / custom GUI. "
            f"Custom GUIs have no direct Bedrock equivalent — consider using block inventory "
            f"components (minecraft:inventory) and reading them via Scripting API, or a FormUI addon."
        )

    static_handlers = _find_static_event_handlers(java_code)

    if not found_methods and not tick_bodies and not static_handlers:
        return False

    needs_permutation = _needs_repair_helper(static_handlers)
    needs_system = bool(tick_bodies)
    imports_parts = ["world"]
    if needs_system:
        imports_parts.append("system")
    imports_parts += ["GameMode", "ItemStack"]
    if needs_permutation:
        imports_parts.append("BlockPermutation")
    base_imports = ", ".join(imports_parts)
    script_lines = [f'import {{ {base_imports} }} from "@minecraft/server";', '']


    for method_name, phase, bedrock_event, entity_ref, body in found_methods:
        translated = _translate_use_body(body, namespace, safe_name)
        script_lines += [
            f'// {method_name}() → {bedrock_event}',
            f'world.{phase}.{bedrock_event}.subscribe((event) => {{',
            f'    const block = event.block;',
            f'    if (!block || block.typeId !== "{block_id}") return;',
            f'    const actor = {entity_ref};',
            f'    if (!actor) return;',
        ] + translated + ['});', '']


    if tick_bodies:
        script_lines += [
            f'// Periodic tick behavior ported from: {", ".join(m for m, _ in tick_bodies)}',
            f'// Uses system.runInterval — adjust interval as needed (20 = once per second)',
            f'system.runInterval(() => {{',
            f'    for (const dimName of ["overworld", "nether", "the_end"]) {{',
            f'        const dim = world.getDimension(dimName);',
            f'        // world.afterEvents.blockRandomTick is available in @minecraft/server ≥1.9',
            f'        // For older packs, iterate nearby blocks manually:',
        ]
        for method_name, body in tick_bodies:
            if body:
                translated = _translate_use_body(body, namespace, safe_name)
                script_lines += [f'        // === {method_name} ==='] + [
                    '    ' + l if l.strip() else l for l in translated
                ]
            else:
                script_lines.append(f'        // TODO: {method_name} — fill in block-entity tick logic here')
        script_lines += [
            '    }',
            '}, 20);',
            '',
        ]

        script_lines += [
            f'// Modern alternative: use world.afterEvents.blockRandomTick (requires @minecraft/server ≥1.9):',
            f'// world.afterEvents.blockRandomTick.subscribe((event) => {{',
            f'//     if (event.block.typeId !== "{block_id}") return;',
            f'//     // tick logic here',
            f'// }});',
            '',
        ]

    for _, event_type, phase, bedrock_event, param, body in static_handlers:
        if script_lines[-1] != '':
            script_lines.append('')
        translated = _translate_handler_body(body, event_type, param, java_code, namespace, safe_name)
        script_lines += [f'world.{phase}.{bedrock_event}.subscribe(({param}) => {{'] + translated + ['});']

    if _needs_repair_helper(static_handlers):
        script_lines += [''] + _emit_repair_helper()

    out_path = os.path.join(BP_FOLDER, "scripts", f"block_{safe_name}.js")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(script_lines))
    print(f"[block-script] Wrote {out_path}")
    return True

def _finish_block_json(doc: dict, safe_name: str) -> None:
    out_path = os.path.join(BP_FOLDER, "blocks", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    safe_write_json(out_path, doc)
    print(f"[block] Wrote {out_path}")
_EFFECT_NAME_MAP = {
    "SPEED": "speed", "SLOWNESS": "slowness", "HASTE": "haste",
    "MINING_FATIGUE": "mining_fatigue", "STRENGTH": "strength",
    "INSTANT_HEALTH": "instant_health", "INSTANT_DAMAGE": "instant_damage",
    "JUMP_BOOST": "jump_boost", "NAUSEA": "nausea", "REGENERATION": "regeneration",
    "RESISTANCE": "resistance", "FIRE_RESISTANCE": "fire_resistance",
    "WATER_BREATHING": "water_breathing", "INVISIBILITY": "invisibility",
    "BLINDNESS": "blindness", "NIGHT_VISION": "night_vision", "HUNGER": "hunger",
    "WEAKNESS": "weakness", "POISON": "poison", "WITHER": "wither",
    "HEALTH_BOOST": "health_boost", "ABSORPTION": "absorption",
    "SATURATION": "saturation", "GLOWING": "glowing", "LEVITATION": "levitation",
    "LUCK": "luck", "UNLUCK": "unluck", "SLOW_FALLING": "slow_falling",
    "CONDUIT_POWER": "conduit_power", "DOLPHINS_GRACE": "dolphins_grace",
    "BAD_OMEN": "bad_omen", "HERO_OF_THE_VILLAGE": "hero_of_the_village",
    "DARKNESS": "darkness",
}

_SOUND_NAME_MAP = {
    "EXPERIENCE_ORB_PICKUP": "random.orb", "ITEM_PICKUP": "random.pop",
    "ENTITY_PLAYER_LEVELUP": "random.levelup", "ENTITY_PLAYER_HURT": "game.player.hurt",
    "ENTITY_PLAYER_DEATH": "game.player.die", "BLOCK_GLASS_BREAK": "random.glass",
    "ENTITY_GENERIC_EXPLODE": "random.explode", "ENTITY_LIGHTNING_BOLT_THUNDER": "ambient.weather.thunder",
    "ENTITY_ENDER_DRAGON_GROWL": "mob.enderdragon.growl", "BLOCK_ANVIL_USE": "random.anvil_use",
    "ENTITY_ARROW_SHOOT": "random.bow", "ENTITY_FIREWORK_ROCKET_LAUNCH": "firework.launch",
}

def _extract_method_body(java_code: str, method_name: str) -> str:
    pattern = (
        r'(?:@Override\s+)?(?:public|protected|private)\s+\S+(?:<[^>]+>)?\s+'
        + re.escape(method_name)
        + r'\s*\([^)]*\)\s*\{'
    )
    m = re.search(pattern, java_code, re.DOTALL)
    if not m:
        return ""
    start = m.end() - 1
    depth, i = 0, start
    while i < len(java_code):
        if java_code[i] == '{':
            depth += 1
        elif java_code[i] == '}':
            depth -= 1
            if depth == 0:
                return java_code[start:i + 1]
        i += 1
    return ""

def _translate_use_body(body: str, namespace: str, safe_name: str) -> list:
    lines = []

    effect_hits = re.findall(
        r'new\s+MobEffectInstance\s*\(\s*MobEffects\.(\w+)\s*,\s*(\d+)\s*(?:,\s*(\d+))?',
        body
    )
    for hit in effect_hits:
        effect_key, duration_ticks, amplifier = hit
        bedrock_effect = _EFFECT_NAME_MAP.get(effect_key, effect_key.lower())
        duration_sec = int(duration_ticks) / 20
        amp = int(amplifier) if amplifier else 0
        lines.append(f'        player.addEffect("minecraft:{bedrock_effect}", {duration_sec}, {{ amplifier: {amp}, showParticles: true }});')

    sound_hits = re.findall(r'SoundEvents\.(\w+)', body)
    for hit in sound_hits:
        bedrock_sound = _SOUND_NAME_MAP.get(hit, "random.pop")
        lines.append(f'        player.dimension.playSound("{bedrock_sound}", player.location);')

    if re.search(r'player\.heal\s*\(|setHealth\s*\(', body):
        heal_m = re.search(r'player\.heal\s*\(\s*([0-9.f]+)', body)
        amount = float(heal_m.group(1).rstrip('f')) if heal_m else 4.0
        lines.append(f'        const health = player.getComponent("minecraft:health");')
        lines.append(f'        if (health) health.setCurrentValue(Math.min(health.currentValue + {amount}, health.effectiveMax));')

    entity_hits = re.findall(
        r'(?:addFreshEntity|summon|spawnEntity)\s*\(\s*new\s+(\w+)\s*\(', body
    )
    for hit in entity_hits:
        entity_id = f"{namespace}:{sanitize_identifier(hit)}"
        lines.append(f'        player.dimension.spawnEntity("{entity_id}", player.location);')

    if re.search(r'player\.setOnFire\s*\(|setSecondsOnFire\s*\(', body):
        fire_m = re.search(r'setOnFire\s*\(\s*(\d+)', body) or re.search(r'setSecondsOnFire\s*\(\s*(\d+)', body)
        seconds = int(fire_m.group(1)) if fire_m else 5
        lines.append(f'        player.setOnFire({seconds});')

    if re.search(r'player\.teleportTo\s*\(|player\.teleport\s*\(', body):
        tp_m = re.search(r'(?:teleportTo|teleport)\s*\(\s*([0-9.-]+)\s*,\s*([0-9.-]+)\s*,\s*([0-9.-]+)', body)
        if tp_m:
            lines.append(f'        player.teleport({{ x: {tp_m.group(1)}, y: {tp_m.group(2)}, z: {tp_m.group(3)} }});')
        else:
            lines.append(f'        // TODO: player.teleport(targetLocation);')

    cooldown_m = re.search(r'addCooldown\s*\(\s*this\s*,\s*(\d+)', body)
    if cooldown_m:
        ticks = int(cooldown_m.group(1))
        lines.append(f'        player.startItemCooldown("{safe_name}", {ticks});')

    if re.search(r'itemStack\.shrink\s*\(1\)|stack\.shrink\s*\(1\)', body):
        lines.append(f'        const inv = player.getComponent("minecraft:inventory");')
        lines.append(f'        if (inv) {{ const slot = inv.container.getSlot(player.selectedSlotIndex); slot.amount = Math.max(0, slot.amount - 1); }}')


    explode_m = re.search(r'(?:explode|createExplosion)\s*\([^,)]*,\s*([0-9.f]+)', body)
    if explode_m:
        power = float(explode_m.group(1).rstrip('f'))
        lines.append(f'        player.dimension.createExplosion(player.location, {power}, {{ breaksBlocks: true }});')


    xp_m = re.search(r'(?:addXp|giveExperiencePoints|giveExperience|addExperience)\s*\(\s*([0-9]+)', body)
    if xp_m:
        lines.append(f'        player.addExperience({xp_m.group(1)});')


    msg_m = re.search(r'(?:sendSystemMessage|displayClientMessage|sendMessage)\s*\(\s*(?:Component\.(?:literal|translatable)\s*\(\s*)?["\']([^"\']+)["\']', body)
    if msg_m:
        lines.append(f'        player.sendMessage("{msg_m.group(1)}");')
    elif re.search(r'(?:sendSystemMessage|displayClientMessage|sendMessage)\s*\(', body):
        lines.append(f'        // TODO: player.sendMessage("...");')


    setblock_m = re.search(r'(?:setBlockAndUpdate|setBlock)\s*\([^,]+,\s*Blocks\.(\w+)', body)
    if setblock_m:
        bedrock_block = f"minecraft:{setblock_m.group(1).lower()}"
        lines.append(f'        // TODO: block.setPermutation(BlockPermutation.resolve("{bedrock_block}"));')


    sched_m = re.search(r'(?:scheduleTick|scheduleBlockTick)\s*\([^,]+,\s*[^,]+,\s*(\d+)', body)
    if sched_m:
        delay = int(sched_m.group(1))
        lines.append(f'        system.runTimeout(() => {{')
        lines.append(f'            // TODO: scheduled tick logic (originally {delay} game ticks)')
        lines.append(f'        }}, {delay});')


    particle_m = re.search(r'addParticle\s*\(\s*(\w+(?:\.\w+)*)\s*,', body)
    if particle_m:
        java_particle = particle_m.group(1).split(".")[-1].lower()
        bedrock_particle = JAVA_PARTICLE_MAP.get(java_particle, "minecraft:enchantment_table_particle")
        lines.append(f'        player.dimension.spawnParticle("{bedrock_particle}", player.location);')


    vel_m = re.search(r'setDeltaMovement\s*\(\s*([0-9.-]+)\s*,\s*([0-9.-]+)\s*,\s*([0-9.-]+)', body)
    if vel_m:
        lines.append(f'        player.applyImpulse({{ x: {vel_m.group(1)}, y: {vel_m.group(2)}, z: {vel_m.group(3)} }});')


    nbt_set = re.search(r'getPersistentData\(\)\.put(?:Int|Float|Double|Boolean|String)\s*\(\s*["\'](\w+)["\']', body)
    if nbt_set:
        lines.append(f'        // TODO: entity.setDynamicProperty("{namespace}:{nbt_set.group(1)}", value);')

    return lines


_ENTITY_SCRIPT_METHODS: Dict[str, Tuple[str, str, str]] = {

    "hurt":                  ("afterEvents", "entityHurt",               "event.hurtEntity"),
    "die":                   ("afterEvents", "entityDie",                "event.deadEntity"),
    "doHurtTarget":          ("afterEvents", "entityHitEntity",          "event.damagingEntity"),
    "performAttack":         ("afterEvents", "entityHitEntity",          "event.damagingEntity"),
    "interact":              ("afterEvents", "playerInteractWithEntity",  "event.target"),
    "interactAt":            ("afterEvents", "playerInteractWithEntity",  "event.target"),
    "onAddedToWorld":        ("afterEvents", "entitySpawn",              "event.entity"),
    "mobInteract":           ("afterEvents", "playerInteractWithEntity",  "event.target"),
    "shoot":                 ("afterEvents", "projectileHitEntity",      "event.projectile"),
    "onProjectileHit":       ("afterEvents", "projectileHitEntity",      "event.projectile"),
}

_ENTITY_TICK_METHODS: List[str] = [
    "tick", "aiStep", "customServerAiStep", "serverAiStep", "baseTick", "rideTick"
]


def _translate_entity_body(body: str, namespace: str, safe_name: str) -> list:
    lines = []


    for hit in re.findall(
        r'new\s+MobEffectInstance\s*\(\s*MobEffects\.(\w+)\s*,\s*(\d+)\s*(?:,\s*(\d+))?',
        body
    ):
        effect_key, dur, amp = hit
        bedrock_effect = _EFFECT_NAME_MAP.get(effect_key, effect_key.lower())
        lines.append(
            f'            entity.addEffect("minecraft:{bedrock_effect}", {int(dur)/20}, '
            f'{{ amplifier: {int(amp) if amp else 0}, showParticles: true }});'
        )


    for hit in re.findall(r'SoundEvents\.(\w+)', body):
        bedrock_sound = _SOUND_NAME_MAP.get(hit, "random.pop")
        lines.append(f'            entity.dimension.playSound("{bedrock_sound}", entity.location);')


    heal_m = re.search(r'(?:heal|setHealth)\s*\(\s*([0-9.f]+)', body)
    if heal_m:
        amount = float(heal_m.group(1).rstrip('f'))
        lines.append(f'            const health = entity.getComponent("minecraft:health");')
        lines.append(f'            if (health) health.setCurrentValue(Math.min(health.currentValue + {amount}, health.effectiveMax));')


    hurt_m = re.search(r'(?<!player\.)(?:hurt|damage)\s*\(\s*[^,)]+,\s*([0-9.f]+)', body)
    if hurt_m:
        lines.append(f'            entity.applyDamage({float(hurt_m.group(1).rstrip("f"))});')


    fire_m = re.search(r'(?:setOnFire|setSecondsOnFire)\s*\(\s*(\d+)', body)
    if fire_m:
        lines.append(f'            entity.setOnFire({int(fire_m.group(1))});')


    for hit in re.findall(r'(?:addFreshEntity|summon|spawnEntity)\s*\(\s*new\s+(\w+)\s*\(', body):
        eid = f"{namespace}:{sanitize_identifier(hit)}"
        lines.append(f'            entity.dimension.spawnEntity("{eid}", entity.location);')


    explode_m = re.search(r'(?:explode|createExplosion)\s*\([^,)]*,\s*([0-9.f]+)', body)
    if explode_m:
        power = float(explode_m.group(1).rstrip('f'))
        lines.append(f'            entity.dimension.createExplosion(entity.location, {power}, {{ breaksBlocks: true }});')


    particle_m = re.search(r'addParticle\s*\(\s*(\w+(?:\.\w+)*)\s*,', body)
    if particle_m:
        java_particle = particle_m.group(1).split(".")[-1].lower()
        bedrock_particle = JAVA_PARTICLE_MAP.get(java_particle, "minecraft:enchantment_table_particle")
        lines.append(f'            entity.dimension.spawnParticle("{bedrock_particle}", entity.location);')


    tp_m = re.search(r'(?:teleportTo|moveTo)\s*\(\s*([0-9.-]+)\s*,\s*([0-9.-]+)\s*,\s*([0-9.-]+)', body)
    if tp_m:
        lines.append(f'            entity.teleport({{ x: {tp_m.group(1)}, y: {tp_m.group(2)}, z: {tp_m.group(3)} }});')
    elif re.search(r'teleportTo\s*\(|teleport\s*\(', body):
        lines.append(f'            // TODO: entity.teleport(targetLocation);')


    vel_m = re.search(r'setDeltaMovement\s*\(\s*([0-9.-]+)\s*,\s*([0-9.-]+)\s*,\s*([0-9.-]+)', body)
    if vel_m:
        lines.append(f'            entity.applyImpulse({{ x: {vel_m.group(1)}, y: {vel_m.group(2)}, z: {vel_m.group(3)} }});')


    if re.search(r'(?:remove|discard)\s*\(\s*\)', body):
        lines.append(f'            entity.remove();')


    for m in re.findall(r'entityData\.set\s*\(\s*(\w+)\s*,\s*(.+?)\s*\)', body):
        field_ref, value_expr = m
        v = value_expr.strip()
        if re.match(r'^[0-9.-]+$', v) or v in ("true", "false"):
            lines.append(f'            entity.setDynamicProperty("{namespace}:{safe_name}_{field_ref.lower()}", {v});')
        else:
            lines.append(f'            // TODO: entity.setDynamicProperty("{namespace}:{safe_name}_{field_ref.lower()}", value);')


    nbt_m = re.search(r'getPersistentData\(\)\.put(?:Int|Float|Double|Boolean|String)\s*\(\s*["\'](\w+)["\']', body)
    if nbt_m:
        lines.append(f'            // TODO: entity.setDynamicProperty("{namespace}:{nbt_m.group(1)}", value);')

    if not lines:
        lines.append(f'            // TODO: translate {safe_name} entity behavior manually')

    return lines


def generate_entity_dynamic_properties(java_code: str, safe_name: str, namespace: str) -> list:
    lines = []
    for m in re.finditer(
        r'EntityDataAccessor\s*<\s*(\w+)\s*>\s+(\w+)\s*=\s*SynchedEntityData\.defineId\s*\([^)]*EntityDataSerializers\.(\w+)',
        java_code
    ):
        field_name = m.group(2).lower()
        serializer = m.group(3)
        prop_key = f'"{namespace}:{safe_name}_{field_name}"'
        if serializer in ("BOOLEAN",):
            lines.append(f'    e.propertyRegistry.defineEntityBooleanProperty({prop_key}, false);')
        elif serializer in ("INT", "BYTE", "SHORT", "FLOAT", "DOUBLE",):
            lines.append(f'    e.propertyRegistry.defineEntityNumberProperty({prop_key}, 0);')
        elif serializer in ("STRING", "COMPOUND_TAG",):
            lines.append(f'    e.propertyRegistry.defineEntityStringProperty({prop_key}, "");')
        else:
            lines.append(f'    // TODO: dynamic property for {field_name} (serializer={serializer})')
    return lines


def generate_entity_script(java_code: str, safe_name: str, entity_id: str, namespace: str) -> bool:
    script_parts: List[List[str]] = []
    needs_system = False


    tick_bodies = []
    for method_name in _ENTITY_TICK_METHODS:
        body = _extract_method_body(java_code, method_name)
        if body:
            tick_bodies.append((method_name, body))

    if tick_bodies:
        needs_system = True
        tick_lines: List[str] = [
            f'// Tick behavior ported from: {", ".join(m for m, _ in tick_bodies)}',
            f'system.runInterval(() => {{',
            f'    for (const dimName of ["overworld", "nether", "the_end"]) {{',
            f'        let entities;',
            f'        try {{ entities = world.getDimension(dimName).getEntities({{ type: "{entity_id}" }}); }}',
            f'        catch (_) {{ continue; }}',
            f'        for (const entity of entities) {{',
        ]
        for method_name, body in tick_bodies:
            tick_lines.append(f'            // === {method_name} ===')
            tick_lines += _translate_entity_body(body, namespace, safe_name)
        tick_lines += ['        }', '    }', '}, 1);']
        script_parts.append(tick_lines)


    for method_name, (phase, bedrock_event, entity_ref) in _ENTITY_SCRIPT_METHODS.items():
        body = _extract_method_body(java_code, method_name)
        if not body:
            continue
        translated = _translate_entity_body(body, namespace, safe_name)
        ev_lines = [
            f'// {method_name}() → {bedrock_event}',
            f'world.{phase}.{bedrock_event}.subscribe((event) => {{',
            f'    const entity = {entity_ref};',
            f'    if (!entity || entity.typeId !== "{entity_id}") return;',
        ] + translated + ['});']
        script_parts.append(ev_lines)


    dp_lines = generate_entity_dynamic_properties(java_code, safe_name, namespace)
    if dp_lines:
        script_parts.append(
            ['// SynchedEntityData → Bedrock dynamic properties',
             'world.afterEvents.worldInitialize.subscribe((e) => {']
            + dp_lines
            + ['});']
        )


    if re.search(r'AbstractContainerMenu|MenuType|createMenu\s*\(|getMenuType\s*\(', java_code):
        _PORTING_NOTES.append(
            f"[entity] {safe_name}: uses AbstractContainerMenu (custom GUI). "
            f"Custom GUIs have no Bedrock equivalent — use block inventory components or a Form UI addon."
        )


    for event_type, (phase, bedrock_event) in _FORGE_EVENT_MAP.items():
        short = event_type.split(".")[-1]
        pat = (
            r'(?:public|private|protected)\s+(?!static)\w+\s+(\w+)\s*\('
            r'[^)]*?' + re.escape(short) + r'\s+(\w+)[^)]*?\)'
        )
        for m in re.finditer(pat, java_code, re.DOTALL):
            method_name = m.group(1)
            param_name  = m.group(2)
            start = java_code.find('{', m.end())
            if start == -1:
                continue
            depth, i, body = 0, start, ""
            while i < len(java_code):
                if java_code[i] == '{':    depth += 1
                elif java_code[i] == '}':
                    depth -= 1
                    if depth == 0:
                        body = java_code[start:i + 1]
                        break
                i += 1
            if body:
                translated = _translate_handler_body(body, event_type, param_name, java_code, namespace, safe_name)
                ev_lines = [
                    f'// {method_name}() instance @SubscribeEvent → {bedrock_event}',
                    f'world.{phase}.{bedrock_event}.subscribe(({param_name}) => {{',
                ] + translated + ['});']
                script_parts.append(ev_lines)

    if not script_parts:
        return False

    imports = ['world']
    if needs_system:
        imports.append('system')
    all_lines = [f'import {{ {", ".join(imports)} }} from "@minecraft/server";', '']
    for i, part in enumerate(script_parts):
        all_lines += part
        if i < len(script_parts) - 1:
            all_lines.append('')

    out_path = os.path.join(BP_FOLDER, "scripts", f"entity_{safe_name}.js")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(all_lines))
    print(f"[entity-script] Wrote {out_path}")
    return True


_INHERITANCE_GRAPH: Dict[str, str] = {}
_PORTING_NOTES: list = []

def build_inheritance_graph(java_files: Dict[str, str]) -> None:
    global _INHERITANCE_GRAPH
    _INHERITANCE_GRAPH = {}
    for code in java_files.values():
        for m in re.finditer(
            r'\bclass\s+(\w+)\s+extends\s+(\w+)',
            code
        ):
            _INHERITANCE_GRAPH[m.group(1)] = m.group(2)

def resolve_superchain(cls_name: str, max_depth: int = 12) -> List[str]:
    chain = []
    current = cls_name
    seen = set()
    for _ in range(max_depth):
        parent = _INHERITANCE_GRAPH.get(current)
        if not parent or parent in seen:
            break
        chain.append(parent)
        seen.add(parent)
        current = parent
    return chain

def class_extends_any(cls_name: str, targets: Set[str]) -> bool:
    if cls_name in targets:
        return True
    for ancestor in resolve_superchain(cls_name):
        if ancestor in targets:
            return True
    return False

_MIXIN_TARGET_TO_BEDROCK: Dict[str, Tuple[str, str, str]] = {
    "LivingEntity":        ("afterEvents", "entityHurt",              "event.hurtEntity"),
    "Player":              ("afterEvents", "playerInteractWithBlock",  "event.player"),
    "ServerPlayer":        ("afterEvents", "playerInteractWithBlock",  "event.player"),
    "Mob":                 ("afterEvents", "entitySpawn",              "event.entity"),
    "PathfinderMob":       ("afterEvents", "entitySpawn",              "event.entity"),
    "Animal":              ("afterEvents", "entitySpawn",              "event.entity"),
    "Monster":             ("afterEvents", "entitySpawn",              "event.entity"),
    "AbstractArrow":       ("afterEvents", "projectileHitEntity",      "event.projectile"),
    "Arrow":               ("afterEvents", "projectileHitEntity",      "event.projectile"),
    "ThrownPotion":        ("afterEvents", "projectileHitEntity",      "event.projectile"),
    "ItemEntity":          ("afterEvents", "itemStartPickUp",          "event.itemEntity"),
    "BlockEntity":         ("afterEvents", "playerInteractWithBlock",  "event.block"),
    "Level":               ("afterEvents", "worldInitialize",          "event"),
    "ServerLevel":         ("afterEvents", "worldInitialize",          "event"),
    "UseOnContext":        ("afterEvents", "playerInteractWithBlock",  "event"),
    "InteractionHand":     ("afterEvents", "playerInteractWithBlock",  "event"),
}

_INJECT_HEAD_BEDROCK: Dict[str, str] = {
    "tick":          "world.afterEvents.entityHurt",
    "hurt":          "world.afterEvents.entityHurt",
    "die":           "world.afterEvents.entityDie",
    "aiStep":        "world.afterEvents.entitySpawn",
    "interact":      "world.afterEvents.playerInteractWithEntity",
    "interactAt":    "world.afterEvents.playerInteractWithEntity",
    "use":           "world.afterEvents.useItem",
    "attack":        "world.afterEvents.entityHitEntity",
    "performAttack": "world.afterEvents.entityHitEntity",
    "shoot":         "world.afterEvents.projectileHitEntity",
    "onBlockActivated": "world.afterEvents.playerInteractWithBlock",
    "use":           "world.afterEvents.playerInteractWithBlock",
    "playerDestroy": "world.afterEvents.playerBreakBlock",
    "place":         "world.afterEvents.playerPlaceBlock",
    "onRemove":      "world.afterEvents.playerBreakBlock",
    "explode":       "world.afterEvents.explosion",
    "onCraftedBy":   "world.afterEvents.crafted",
    "finishUsingItem": "world.afterEvents.useItem",
    "onEquip":       "world.afterEvents.playerInteractWithBlock",
}

def scan_mixins(java_files: Dict[str, str], namespace: str) -> None:
    for path, code in java_files.items():
        mixin_m = re.search(r'@Mixin\s*\(\s*(?:value\s*=\s*)?(\w+)\.class', code)
        if not mixin_m:
            continue
        target_cls = mixin_m.group(1)
        cls_name = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
        safe_name = sanitize_identifier(cls_name)

        inject_methods = re.findall(
            r'@Inject\s*\([^)]*method\s*=\s*["\'](\w+)["\'][^)]*\)[^{]*'
            r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(',
            code, re.DOTALL
        )
        redirect_methods = re.findall(
            r'@Redirect\s*\([^)]*method\s*=\s*["\'](\w+)["\'][^)]*\)[^{]*'
            r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(',
            code, re.DOTALL
        )
        overwrite_methods = re.findall(
            r'@Overwrite[^{]*(?:public|private|protected)\s+\w+\s+(\w+)\s*\(',
            code, re.DOTALL
        )

        bedrock_info = _MIXIN_TARGET_TO_BEDROCK.get(target_cls)
        if not bedrock_info and target_cls in _INHERITANCE_GRAPH:
            for ancestor in resolve_superchain(target_cls):
                if ancestor in _MIXIN_TARGET_TO_BEDROCK:
                    bedrock_info = _MIXIN_TARGET_TO_BEDROCK[ancestor]
                    break

        script_lines = [f'import {{ world, system }} from "@minecraft/server";', '']
        wrote_anything = False

        for target_method, handler_method in inject_methods:
            bedrock_event = _INJECT_HEAD_BEDROCK.get(target_method)
            if bedrock_event:
                body = _extract_method_body(code, handler_method)
                translated = _translate_use_body(body, namespace, safe_name) if body else []
                script_lines += [
                    f'{bedrock_event}.subscribe((event) => {{',
                ] + (translated if translated else [
                    f'    const entity = event.entity ?? event.player ?? event.hurtEntity;',
                    f'    if (!entity) return;',
                ]) + ['});', '']
                wrote_anything = True
            else:
                _PORTING_NOTES.append(
                    f"[mixin] {cls_name}: @Inject on {target_cls}.{target_method}() "
                    f"has no automatic Bedrock mapping — port manually using Scripting API"
                )

        for target_method, handler_method in redirect_methods:
            _PORTING_NOTES.append(
                f"[mixin] {cls_name}: @Redirect on {target_cls}.{target_method}() "
                f"cannot be automatically translated — @Redirect modifies a specific call site inside a method, "
                f"which has no Bedrock equivalent. Consider rewriting as a separate event subscription."
            )

        for method_name in overwrite_methods:
            body = _extract_method_body(code, method_name)
            bedrock_event = _INJECT_HEAD_BEDROCK.get(method_name)
            if bedrock_event and body:
                translated = _translate_use_body(body, namespace, safe_name)
                script_lines += [
                    f'{bedrock_event}.subscribe((event) => {{',
                ] + (translated if translated else [
                    f'    const entity = event.entity ?? event.player ?? event.hurtEntity;',
                ]) + ['});', '']
                wrote_anything = True
            else:
                _PORTING_NOTES.append(
                    f"[mixin] {cls_name}: @Overwrite of {target_cls}.{method_name}() "
                    f"has no automatic Bedrock mapping — port manually"
                )

        if wrote_anything:
            out_path = os.path.join(BP_FOLDER, "scripts", f"mixin_{safe_name}.js")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(script_lines))
            print(f"[mixin] Wrote {out_path}")

_CAP_FIELD_TYPE_MAP = {
    "int": "number",
    "float": "number",
    "double": "number",
    "long": "number",
    "boolean": "boolean",
    "String": "string",
    "ItemStack": "string",
    "ResourceLocation": "string",
}

def scan_capabilities(java_files: Dict[str, str], namespace: str) -> None:
    for path, code in java_files.items():
        is_cap = bool(re.search(
            r'implements\s+(?:[A-Za-z,\s]*\b(?:ICapabilityProvider|ICapabilitySerializable|INBTSerializable|IEnergyStorage|IFluidHandler)\b)',
            code
        ))
        if not is_cap:
            continue
        cls_name = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
        safe_name = sanitize_identifier(cls_name)

        is_energy = bool(re.search(r'IEnergyStorage', code))
        is_fluid = bool(re.search(r'IFluidHandler', code))

        fields = re.findall(
            r'(?:private|protected|public)\s+(int|float|double|long|boolean|String|ItemStack|ResourceLocation)\s+(\w+)\s*(?:=|;)',
            code
        )
        if not fields and not is_energy and not is_fluid:
            _PORTING_NOTES.append(
                f"[capability] {cls_name}: implements ICapabilityProvider but no simple fields detected — "
                f"convert to Bedrock dynamic properties manually"
            )
            continue

        script_lines = [f'import {{ world }} from "@minecraft/server";', '']


        if is_energy:
            script_lines.append(
                f'world.afterEvents.worldInitialize.subscribe((e) => {{'
            )
            script_lines.append(
                f'    e.propertyRegistry.defineEntityNumberProperty("{namespace}:{safe_name}_energy", 0);'
            )
            script_lines.append('});')
            script_lines.append('')


        if is_fluid:
            script_lines.append(
                f'world.afterEvents.worldInitialize.subscribe((e) => {{'
            )
            script_lines.append(
                f'    e.propertyRegistry.defineEntityNumberProperty("{namespace}:{safe_name}_fluid_amount", 0);'
            )
            script_lines.append(
                f'    e.propertyRegistry.defineEntityStringProperty("{namespace}:{safe_name}_fluid_type", "minecraft:water");'
            )
            script_lines.append('});')
            script_lines.append('')


        if is_energy:
            script_lines += [
                f'function receiveEnergy(entity, amount, simulate = false) {{',
                f'    let current = entity.getDynamicProperty("{namespace}:{safe_name}_energy") || 0;',
                f'    let newAmount = Math.min(current + amount, 1000000); // Assuming max capacity',
                f'    if (!simulate) entity.setDynamicProperty("{namespace}:{safe_name}_energy", newAmount);',
                f'    return newAmount - current;',
                f'}}',
                '',
                f'function extractEnergy(entity, amount, simulate = false) {{',
                f'    let current = entity.getDynamicProperty("{namespace}:{safe_name}_energy") || 0;',
                f'    let extracted = Math.min(current, amount);',
                f'    if (!simulate) entity.setDynamicProperty("{namespace}:{safe_name}_energy", current - extracted);',
                f'    return extracted;',
                f'}}',
                '',
                f'function getEnergyStored(entity) {{',
                f'    return entity.getDynamicProperty("{namespace}:{safe_name}_energy") || 0;',
                f'}}',
                '',
            ]


        if is_fluid:
            script_lines += [
                f'function fill(entity, fluidStack, simulate = false) {{',
                f'    let currentAmount = entity.getDynamicProperty("{namespace}:{safe_name}_fluid_amount") || 0;',
                f'    let currentType = entity.getDynamicProperty("{namespace}:{safe_name}_fluid_type") || "minecraft:water";',
                f'    if (currentAmount > 0 && fluidStack.type !== currentType) return 0;',
                f'    let space = 1000 - currentAmount; // Assuming capacity 1000',
                f'    let filled = Math.min(space, fluidStack.amount);',
                f'    if (!simulate) {{',
                f'        entity.setDynamicProperty("{namespace}:{safe_name}_fluid_amount", currentAmount + filled);',
                f'        entity.setDynamicProperty("{namespace}:{safe_name}_fluid_type", fluidStack.type);',
                f'    }}',
                f'    return filled;',
                f'}}',
                '',
                f'function drain(entity, amount, simulate = false) {{',
                f'    let currentAmount = entity.getDynamicProperty("{namespace}:{safe_name}_fluid_amount") || 0;',
                f'    let drained = Math.min(currentAmount, amount);',
                f'    if (!simulate) {{',
                f'        entity.setDynamicProperty("{namespace}:{safe_name}_fluid_amount", currentAmount - drained);',
                f'    }}',
                f'    return {{ amount: drained, type: entity.getDynamicProperty("{namespace}:{safe_name}_fluid_type") || "minecraft:water" }};',
                f'}}',
                '',
                f'function getFluidAmount(entity) {{',
                f'    return entity.getDynamicProperty("{namespace}:{safe_name}_fluid_amount") || 0;',
                f'}}',
                '',
            ]
            bedrock_type = _CAP_FIELD_TYPE_MAP.get(java_type, "string")
            script_lines.append(
                f'world.afterEvents.worldInitialize.subscribe((e) => {{'
            )
            script_lines.append(
                f'    e.propertyRegistry.defineEntityNumberProperty("{namespace}:{safe_name}_{field_name}", 0);'
                if bedrock_type == "number" else
                f'    e.propertyRegistry.defineEntityStringProperty("{namespace}:{safe_name}_{field_name}", "");'
                if bedrock_type == "string" else
                f'    e.propertyRegistry.defineEntityBooleanProperty("{namespace}:{safe_name}_{field_name}", false);'
            )
            script_lines.append('});')
            script_lines.append('')

        getter_methods = re.findall(
            r'public\s+\S+\s+(get\w+)\s*\(\s*\)',
            code
        )
        setter_methods = re.findall(
            r'public\s+void\s+(set\w+)\s*\(\s*\S+\s+(\w+)\s*\)',
            code
        )

        if getter_methods or setter_methods:
            script_lines += [
                f'function getCapability(entity, key) {{',
                f'    return entity.getDynamicProperty("{namespace}:{safe_name}_" + key);',
                f'}}',
                '',
                f'function setCapability(entity, key, value) {{',
                f'    entity.setDynamicProperty("{namespace}:{safe_name}_" + key, value);',
                f'}}',
                '',
            ]

        out_path = os.path.join(BP_FOLDER, "scripts", f"cap_{safe_name}.js")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(script_lines))
        print(f"[capability] Wrote {out_path}")

_PACKET_HANDLER_PATTERNS = [
    r'SimpleChannel\s*\.\s*(?:newSimpleChannel|create)\s*\(\s*(?:new\s+)?ResourceLocation\s*\(\s*["\']([^"\']+)["\']',
    r'ChannelBuilder\s*\.\s*named\s*\(\s*(?:new\s+)?ResourceLocation\s*\(\s*["\']([^"\']+)["\']',
    r'NetworkRegistry\s*\.\s*newSimpleChannel\s*\(\s*(?:new\s+)?ResourceLocation\s*\(\s*["\']([^"\']+)["\']',
]

def scan_networking(java_files: Dict[str, str], namespace: str) -> None:
    channel_files: dict = {}
    packet_classes: dict = {}                    

    for path, code in java_files.items():
        for pat in _PACKET_HANDLER_PATTERNS:
            m = re.search(pat, code)
            if m:
                channel_files[path] = (code, m.group(1))
                break

        if re.search(
            r'implements\s+(?:[A-Za-z,\s]*\b(?:CustomPacketPayload|FriendlyByteBuf)\b)',
            code
        ):
            cls_name = extract_class_name(code)
            if cls_name:
                packet_classes[cls_name] = code

        for pcls in (
            re.findall(r'\.registerMessage\s*\([^,]+,\s*(\w+)\.class', code) +
            re.findall(r'\.messageBuilder\s*\(\s*(\w+)\.class', code) +
            re.findall(r'\.play\.toClient\(\s*(\w+)\.class', code) +
            re.findall(r'\.play\.toServer\(\s*(\w+)\.class', code)
        ):
            if pcls not in packet_classes:
                packet_classes[pcls] = ""

    if not channel_files and not packet_classes:
        return

    serverbound_lines: list = [
        f'import {{ world, system }} from "@minecraft/server";', ''
    ]
    clientbound_lines: list = []

    def _classify_direction(pcode: str) -> str:
        if re.search(r'void\s+handle\s*\([^)]*(?:Level|ServerLevel|Player|ServerPlayer)[^)]*\)', pcode):
            return 'server'
        if re.search(r'void\s+handle\s*\([^)]*Minecraft[^)]*\)', pcode):
            return 'client'
        if re.search(r'\bServerPayloadHandler\b|\bPlayPayloadHandler\b', pcode):
            return 'server'
        if re.search(r'\bClientPayloadHandler\b', pcode):
            return 'client'
        return 'unknown'

    def _extract_packet_fields(pcode: str) -> list:
        fields = re.findall(
            r'(?:private|public|protected|final)\s+(?:final\s+)?(\w+(?:<[^>]+>)?)\s+(\w+)\s*[;=]',
            pcode
        )

        skip = {'LOGGER', 'HANDLER', 'TYPE', 'STREAM_CODEC', 'ID', 'serialVersionUID'}
        return [(ft, fn) for ft, fn in fields if fn not in skip][:12]

    for pcls, pcode in packet_classes.items():
        safe = sanitize_identifier(pcls)
        direction = _classify_direction(pcode) if pcode else 'unknown'
        fields = _extract_packet_fields(pcode) if pcode else []


        field_lines: list = ['    const data = JSON.parse(event.message);']
        for ftype, fname in fields:
            btype = _CAP_FIELD_TYPE_MAP.get(ftype, 'any')
            cast = '' if btype in ('any', 'string') else (
                'Number(' + f'data.{fname}' + ')'
                if btype == 'number' else
                'Boolean(' + f'data.{fname}' + ')'
                if btype == 'boolean' else
                f'data.{fname}'
            )
            field_lines.append(
                f'    const {fname} = {cast if cast else f"data.{fname}"};')


        handle_body = _extract_method_body(pcode, 'handle') if pcode else ''
        handle_comment = []
        if handle_body:
            for line in handle_body.strip().splitlines()[:8]:
                handle_comment.append(f'    // java: {line.strip()}')

        if direction in ('server', 'unknown'):
            event_id = f'{namespace}:{safe}'
            serverbound_lines += [
                f'// Packet: {pcls}  [{direction}-bound]',
                f'world.afterEvents.scriptEventReceive.subscribe((event) => {{',
                f'    if (event.id !== "{event_id}") return;',
            ] + field_lines + [
                f'    const player = [...world.getAllPlayers()].find(p => p.name === data.sender);',
                f'    if (!player) return;',
            ] + handle_comment + [
                f'    // TODO: implement server logic for {pcls}',
                f'}});',
                '',
            ]
        else:

            event_id = f'client:{namespace}:{safe}'
            clientbound_lines += [
                f'// Client-bound Packet: {pcls}',
                f'// Bedrock has no direct client-side scripting API equivalent.',
                f'// This handler re-emits the data as a "client:" prefixed script event',
                f'// that the UI layer can subscribe to via world.afterEvents.scriptEventReceive.',
                f'world.afterEvents.scriptEventReceive.subscribe((event) => {{',
                f'    if (event.id !== "{event_id}") return;',
            ] + field_lines + [
                f'    // Re-broadcast to all players (or filter by data.target)',
                f'    for (const p of world.getAllPlayers()) {{',
                f'        p.runCommand(`scriptevent {namespace}:{safe}_ack ${{JSON.stringify(data)}}`);',
                f'    }}',
                f'}});',
                '',
            ]

        _PORTING_NOTES.append(
            f"[network] {direction.upper()} packet '{pcls}' → "
            f"scriptEventReceive id='{event_id}'.  "
            f"Java sender must call: world.events.server.execute(() -> "
            f"MinecraftServer#execute('/scriptevent {event_id} {{...}}'))."
        )

    all_lines = serverbound_lines
    if clientbound_lines:
        all_lines += ['// ── Client-bound packets ──', ''] + clientbound_lines

    if all_lines[-1] != '':
        all_lines.append('')

    out_path = os.path.join(BP_FOLDER, "scripts", "network_packets.js")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(all_lines))
    print(f"[network] Wrote {out_path} ({len(packet_classes)} packet class(es))")

_CLIENT_RENDERER_BASES = {
    "EntityRenderer", "MobRenderer", "LivingEntityRenderer",
    "BlockEntityRenderer", "ParticleEngine", "GameRenderer",
    "ItemRenderer", "FontRenderer", "GlStateManager",
    "RenderType", "VertexConsumer", "PoseStack",
    "ShaderInstance", "PostChain",
}

_CLIENT_ONLY_IMPORTS = {
    "net.minecraft.client", "com.mojang.blaze3d", "net.minecraftforge.client",
    "net.neoforged.neoforge.client", "net.fabricmc.fabric.api.client",
}

def detect_client_only(java_code: str, cls_name: str) -> Optional[str]:
    for imp in _CLIENT_ONLY_IMPORTS:
        if f"import {imp}" in java_code:
            return f"uses client-only import package {imp}"

    superclass_m = re.search(r'\bextends\s+(\w+)', java_code)
    if superclass_m:
        base = superclass_m.group(1)
        if base in _CLIENT_RENDERER_BASES:
            return f"extends {base}"
        for ancestor in resolve_superchain(base):
            if ancestor in _CLIENT_RENDERER_BASES:
                return f"extends {base} (which extends {ancestor})"

    if re.search(r'@OnlyIn\s*\(\s*Dist\.CLIENT\s*\)|@Environment\s*\(\s*EnvType\.CLIENT\s*\)', java_code):
        return "@OnlyIn(Dist.CLIENT) annotation"

    return None

def scan_client_classes(java_files: Dict[str, str]) -> None:
    for path, code in java_files.items():
        cls_name = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
        reason = detect_client_only(code, cls_name)
        if reason:
            _PORTING_NOTES.append(
                f"[client-only] {cls_name} ({reason}): "
                f"client-side rendering has no Bedrock equivalent. "
                f"Textures/models are handled by the RP; custom shaders and render layers cannot be ported."
            )

def write_porting_notes() -> None:
    if not _PORTING_NOTES:
        return
    out_path = os.path.join(OUTPUT_DIR, "PORTING_NOTES.txt")
    categories = {"mixin": [], "capability": [], "network": [], "client-only": [], "other": []}
    for note in _PORTING_NOTES:
        matched = False
        for cat in categories:
            if note.startswith(f"[{cat}]"):
                categories[cat].append(note)
                matched = True
                break
        if not matched:
            categories["other"].append(note)
    lines = [
        "ModMorpher — Porting Notes",
        "=" * 60,
        "",
        "These items could not be automatically converted and require",
        "manual attention before the addon will be fully functional.",
        "",
    ]
    section_titles = {
        "mixin": "Mixin Injections",
        "capability": "Capability Providers",
        "network": "Network Packets",
        "client-only": "Client-Side Rendering",
        "other": "Other",
    }
    for cat, notes in categories.items():
        if not notes:
            continue
        lines += [section_titles[cat], "-" * len(section_titles[cat])]
        for note in notes:
            body = re.sub(r'^\[' + cat + r'\]\s*', '', note)
            lines.append(f"  {body}")
        lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[notes] Wrote {out_path} ({len(_PORTING_NOTES)} item(s))")

_FORGE_EVENT_MAP = {
    "PlayerInteractEvent.EntityInteract":  ("afterEvents", "playerInteractWithEntity"),
    "PlayerInteractEvent.RightClickBlock": ("afterEvents", "playerInteractWithBlock"),
    "PlayerInteractEvent.RightClickItem":  ("afterEvents", "useItem"),
    "PlayerInteractEvent.LeftClickBlock":  ("afterEvents", "playerBreakBlock"),
    "LivingHurtEvent":                     ("afterEvents", "entityHurt"),
    "LivingDeathEvent":                    ("afterEvents", "entityDie"),
    "BlockEvent.BreakEvent":               ("afterEvents", "playerBreakBlock"),
    "BlockEvent.PlaceEvent":               ("afterEvents", "playerPlaceBlock"),
    "EntityJoinLevelEvent":                ("afterEvents", "entitySpawn"),
    "ItemCraftedEvent":                    ("afterEvents", "crafted"),
    "PlayerEvent.ItemPickupEvent":         ("afterEvents", "itemStartPickUp"),
}

def _find_static_event_handlers(java_code: str) -> list:
    handlers = []
    seen = set()
    for event_type, (phase, bedrock_event) in _FORGE_EVENT_MAP.items():
        short = event_type.split(".")[-1]
        pat = (
            r'(?:(?:public|private|protected)\s+)?static\s+\w+\s+(\w+)\s*\('
            r'[^)]*?' + re.escape(short) + r'\s+(\w+)[^)]*?\)'
        )
        for m in re.finditer(pat, java_code, re.DOTALL):
            method_name = m.group(1)
            if method_name in seen:
                continue
            seen.add(method_name)
            param_name = m.group(2)
            start = java_code.find('{', m.end())
            if start == -1:
                continue
            depth, i = 0, start
            body = ""
            while i < len(java_code):
                if java_code[i] == '{':
                    depth += 1
                elif java_code[i] == '}':
                    depth -= 1
                    if depth == 0:
                        body = java_code[start:i + 1]
                        break
                i += 1
            if body:
                handlers.append((method_name, event_type, phase, bedrock_event, param_name, body))
    return handlers

def _extract_tag_path(java_code: str, field_name: str) -> Optional[str]:
    pat = (
        r'\b' + re.escape(field_name) + r'\b[^=\n]*=\s*TagKey\.create\s*\([^,]+,\s*'
        r'ResourceLocation\.(?:fromNamespaceAndPath|of|parse|withDefaultNamespace)\s*\('
        r'[^,)]+,\s*["\']([^"\']+)["\']'
    )
    m = re.search(pat, java_code, re.DOTALL)
    if m:
        return m.group(1)
    pat2 = (
        r'\b' + re.escape(field_name) + r'\b[^=\n]*=\s*TagKey\.create\s*\([^,]+,\s*'
        r'new\s+ResourceLocation\s*\([^,)]+,\s*["\']([^"\']+)["\']'
    )
    m2 = re.search(pat2, java_code, re.DOTALL)
    return m2.group(1) if m2 else None

def _get_player_var(event_type: str, param: str) -> str:
    player_events = {
        "PlayerInteractEvent.EntityInteract",
        "PlayerInteractEvent.RightClickBlock",
        "PlayerInteractEvent.RightClickItem",
        "PlayerInteractEvent.LeftClickBlock",
        "ItemCraftedEvent",
        "PlayerEvent.ItemPickupEvent",
    }
    if event_type in player_events:
        return f"{param}.player"
    if event_type in ("LivingHurtEvent", "LivingDeathEvent"):
        return f"{param}.entity"
    return f"{param}.player"

def _translate_handler_body(java_body: str, event_type: str, param: str, java_code_full: str, namespace: str, safe_name: str) -> list:


    lines = []
    player = _get_player_var(event_type, param)


    ast_lines = JavaAST.translate_java_body_to_js(java_body, event_type, param, namespace, safe_name)
    if ast_lines:
        lines.extend(ast_lines)
    else:

        needs_inv = bool(re.search(r'\.shrink\s*\(|\.addItem\s*\(|getItemStack\s*\(', java_body))
        needs_block = bool(re.search(r'setBlock\s*\(|getBlockState\s*\(|getBlockPos\s*\(|getHitVec\s*\(', java_body))

        if needs_inv:
            lines.append(f'    const inv = {player}.getComponent("minecraft:inventory").container;')
            lines.append(f'    const heldSlot = {player}.selectedSlotIndex;')
            lines.append(f'    let heldItem = inv.getItem(heldSlot);')

        if event_type == "PlayerInteractEvent.RightClickBlock" and needs_block:
            lines.append(f'    const block = {param}.block;')

        if event_type == "PlayerInteractEvent.EntityInteract":
            lines.append(f'    const target = {param}.target;')

        if re.search(r'isCrouching\s*\(\s*\)|isSneaking\s*\(\s*\)', java_body):
            lines.append(f'    if (!{player}.isSneaking) return;')

        null_checks = re.findall(r'(\w+)\s*!=\s*null', java_body)
        entity_null = any(c in ("entityInteractEvent", param, "entity", "player") for c in null_checks)
        if not entity_null and re.search(r'getEntity\s*\(\s*\)\s*!=\s*null', java_body):
            lines.append(f'    if (!{player}) return;')

        target_type_check = re.search(
            r'getTarget\s*\(\s*\)\.getType\s*\(\s*\)\.is\s*\(\s*(\w+(?:\.\w+)*)\s*\)',
            java_body
        )
        if target_type_check:
            ref = target_type_check.group(1).split(".")[-1]
            tag_path = _extract_tag_path(java_code_full, ref)
            entity_hint = sanitize_identifier(tag_path.split("_for_")[0] if tag_path and "_for_" in tag_path else (tag_path or ref))
            lines.append(f'    if (!target || !target.typeId.includes("{entity_hint}")) return;')

        item_is_checks = re.findall(r'(?:getItemStack\s*\(\s*\)|stack|itemStack)\.is\s*\(\s*(\w+)\s*\)', java_body)
        for tag_ref in item_is_checks:
            lines.append(f'    if (!heldItem || heldItem.typeId !== "{namespace}:{sanitize_identifier(tag_ref)}") return;')
        item_identity_check = re.search(
            r'(?:stack|itemStack|heldStack)\.is\s*\(\s*(\w+(?:\.\w+)*)\s*\)',
            java_body
        )

        if item_identity_check and not item_is_checks:
            ref = item_identity_check.group(1).split(".")[-1]
            lines.append(f'    if (!heldItem || heldItem.typeId !== "{namespace}:{sanitize_identifier(ref)}") return;')

        repair_call = bool(re.search(r'repairState\s*\(', java_body))
        if repair_call:
            lines.append(f'    const repairedId = repairBlockId(block.typeId);')
            lines.append(f'    if (!repairedId) return;')

        hurt_break = re.search(r'hurtAndBreak\s*\(\s*(\d+)', java_body)
        if hurt_break:
            dmg = int(hurt_break.group(1))
            lines.append(f'    const dur = heldItem?.getComponent("minecraft:durability");')
            lines.append(f'    if (dur) {{ dur.damage = Math.min(dur.damage + {dmg}, dur.maxDurability); inv.setItem(heldSlot, heldItem); }}')

        if re.search(r'level\.setBlock\s*\(', java_body):
            if repair_call:
                lines.append(f'    block.setPermutation(BlockPermutation.resolve(repairedId));')
            else:
                lines.append(f'    block.setPermutation(block.permutation);')

        play_sound = re.search(
            r'playSound\s*\([^,]+,\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*SoundEvents\.(\w+)',
            java_body
        )
        if play_sound:
            bedrock_sound = _SOUND_NAME_MAP.get(play_sound.group(1), "random.pop")
            lines.append(f'    {player}.dimension.playSound("{bedrock_sound}", {player}.location);')

        if re.search(r'\.swing\s*\(', java_body):
            lines.append(f'    {player}.playAnimation("animation.player.attack.rotations");')

        instabuild = bool(re.search(r'getAbilities\s*\(\s*\)\.instabuild|isCreative\s*\(\s*\)', java_body))
        shrink = re.search(r'(?:getItemStack\s*\(\s*\)|stack|itemStack)\.shrink\s*\(\s*(\d+)\s*\)', java_body)
        if shrink:
            amt = int(shrink.group(1))
            if instabuild:
                lines.append(f'    if ({player}.getGameMode() !== GameMode.creative) {{')
                lines.append(f'        if (heldItem) {{ heldItem.amount = Math.max(0, heldItem.amount - {amt}); inv.setItem(heldSlot, heldItem.amount <= 0 ? undefined : heldItem); }}')
                lines.append(f'    }}')
            else:
                lines.append(f'    if (heldItem) {{ heldItem.amount = Math.max(0, heldItem.amount - {amt}); inv.setItem(heldSlot, heldItem.amount <= 0 ? undefined : heldItem); }}')

        add_item = re.search(r'addItem\s*\(([^;]+)\)', java_body)
        if add_item:
            arg = add_item.group(1).strip()
            const_m = re.search(r'\.([A-Z][A-Z0-9_]+)\b', arg)
            if const_m:
                const_name = const_m.group(1)
                reg_m = re.search(
                    r'\b' + re.escape(const_name) + r'\b[^\n]*register\s*\(\s*["\']([a-z0-9_]+)["\']',
                    java_code_full, re.I
                )
                item_name = reg_m.group(1) if reg_m else sanitize_identifier(const_name)
            else:
                plain = arg.split(".")[0].strip()
                item_name = sanitize_identifier(plain)
            lines.append(f'    inv.addItem(new ItemStack("{namespace}:{item_name}"));')


        energy_receive = re.search(r'energy\.receiveEnergy\s*\(\s*(\d+)\s*\)', java_body)
        if energy_receive:
            amt = energy_receive.group(1)
            lines.append(f'    receiveEnergy({player}, {amt});')

        energy_extract = re.search(r'energy\.extractEnergy\s*\(\s*(\d+)\s*\)', java_body)
        if energy_extract:
            amt = energy_extract.group(1)
            lines.append(f'    extractEnergy({player}, {amt});')

        fluid_fill = re.search(r'fluid\.fill\s*\(\s*(\w+),\s*(\d+)\s*\)', java_body)
        if fluid_fill:
            fluid_type = fluid_fill.group(1)
            amt = fluid_fill.group(2)
            lines.append(f'    fill({player}, {{ type: "{namespace}:{fluid_type}", amount: {amt} }});')

        fluid_drain = re.search(r'fluid\.drain\s*\(\s*(\d+)\s*\)', java_body)
        if fluid_drain:
            amt = fluid_drain.group(1)
            lines.append(f'    drain({player}, {amt});')

    return lines

def _needs_repair_helper(handlers: list) -> bool:
    return any(re.search(r'repairState\s*\(', body) for _, _, _, _, _, body in handlers)

def _emit_repair_helper() -> list:
    return [
        'function repairBlockId(typeId) {',
        '    const path = typeId.replace(/^minecraft:/, "");',
        '    let modified = path',
        '        .replace(/^damaged_/, "chipped_")',
        '        .replace(/_damaged$/, "_chipped")',
        '        .replace(/_damaged_/, "_chipped_");',
        '    if (modified !== path) return "minecraft:" + modified;',
        '    for (const word of ["cracked", "mossy", "polished", "chiseled", "smooth", "cut", "chipped"]) {',
        '        modified = path',
        '            .replace(new RegExp("^" + word + "_"), "")',
        '            .replace(new RegExp("_" + word + "$"), "")',
        '            .replace(new RegExp("_" + word + "_"), "_");',
        '        if (modified !== path) return "minecraft:" + modified;',
        '    }',
        '    return null;',
        '}',
    ]

def generate_scripting_stub(java_code: str, safe_name: str, item_id: str, namespace: str) -> bool:
    use_body        = _extract_method_body(java_code, "use")
    hurt_body       = _extract_method_body(java_code, "hurtEnemy")
    tick_body       = _extract_method_body(java_code, "inventoryTick")
    finish_body     = _extract_method_body(java_code, "finishUsingItem")
    crafted_body    = _extract_method_body(java_code, "onCraftedBy")
    static_handlers = _find_static_event_handlers(java_code)

    has_instance_methods = any([use_body, hurt_body, tick_body, finish_body, crafted_body])
    if not has_instance_methods and not static_handlers:
        return False

    needs_permutation = _needs_repair_helper(static_handlers)
    needs_system      = bool(tick_body)
    imports_parts     = ["world"]
    if needs_system:
        imports_parts.append("system")
    imports_parts += ["GameMode", "ItemStack"]
    if needs_permutation:
        imports_parts.append("BlockPermutation")
    base_imports = ", ".join(imports_parts)
    script_lines = [f'import {{ {base_imports} }} from "@minecraft/server";', '']

    if has_instance_methods:
        script_lines += [
            f'const COMPONENT_ID = "{namespace}:{safe_name}_use";',
            '',
            'class UseHandler {',
        ]
        if use_body:
            translated = _translate_use_body(use_body, namespace, safe_name)
            script_lines += ['    onUse(event) {', '        const player = event.source;', '        if (!player) return;'] + translated + ['    }']
        if hurt_body:
            translated = _translate_use_body(hurt_body, namespace, safe_name)
            script_lines += ['    onHitEntity(event) {', '        const player = event.attackingEntity;', '        if (!player) return;'] + translated + ['    }']
        if finish_body:

            translated = _translate_use_body(finish_body, namespace, safe_name)
            script_lines += ['    onConsume(event) {', '        const player = event.source;', '        if (!player) return;'] + translated + ['    }']
        if crafted_body:
            script_lines += [
                '    // onCraftedBy → subscribe via world.afterEvents.crafted instead of a component method',
                '    // See the world.afterEvents.crafted.subscribe block below.',
            ]
        if tick_body:

            script_lines += [
                '    // inventoryTick has no direct item-component callback.',
                '    // Handled by the system.runInterval block below.',
            ]
        script_lines += [
            '}',
            '',
            'world.beforeEvents.worldInitialize.subscribe((e) => {',
            f'    e.itemComponentRegistry.registerCustomComponent(COMPONENT_ID, new UseHandler());',
            '});',
            '',
        ]


    if tick_body:
        translated = _translate_use_body(tick_body, namespace, safe_name)
        script_lines += [
            f'// inventoryTick() → scan every player inventory each tick',
            f'system.runInterval(() => {{',
            f'    for (const player of world.getAllPlayers()) {{',
            f'        const inv = player.getComponent("minecraft:inventory")?.container;',
            f'        if (!inv) continue;',
            f'        for (let i = 0; i < inv.size; i++) {{',
            f'            const item = inv.getItem(i);',
            f'            if (!item || item.typeId !== "{item_id}") continue;',
        ] + ['            ' + l.strip() for l in translated] + [
            '        }',
            '    }',
            '}, 1);',
            '',
        ]


    if crafted_body:
        translated = _translate_use_body(crafted_body, namespace, safe_name)
        script_lines += [
            f'// onCraftedBy() → crafted event',
            f'world.afterEvents.crafted.subscribe((event) => {{',
            f'    if (!event.craftingSlots) return;',
            f'    const result = event.craftingSlots[0]?.item;',
            f'    if (!result || result.typeId !== "{item_id}") return;',
            f'    const player = event.player;',
            f'    if (!player) return;',
        ] + translated + ['});', '']

    for _, event_type, phase, bedrock_event, param, body in static_handlers:
        if script_lines and script_lines[-1] != '':
            script_lines.append('')
        translated = _translate_handler_body(body, event_type, param, java_code, namespace, safe_name)
        script_lines += [f'world.{phase}.{bedrock_event}.subscribe(({param}) => {{'] + translated + ['});']

    if _needs_repair_helper(static_handlers):
        script_lines += [''] + _emit_repair_helper()

    out_path = os.path.join(BP_FOLDER, "scripts", f"{safe_name}.js")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(script_lines))
    print(f"[script] Wrote {out_path}")
    return True

def convert_java_item_full(java_code: str, java_path: str, namespace: str):
    cls = extract_class_name(java_code) or os.path.splitext(os.path.basename(java_path))[0]
    safe_name = sanitize_identifier(cls)
    item_id = f"{namespace}:{safe_name}"
    max_stack = 64
    m = re.search(r'(?:maxStackSize|stacksTo)\s*\(?\s*(\d+)', java_code, re.I)
    if m:
        max_stack = int(m.group(1))
    durability = 0
    m2 = re.search(r'(?:maxDamage|durability|defaultDurability)\s*\(?\s*(\d+)', java_code, re.I)
    if m2:
        durability = int(m2.group(1))
    components = {
        "minecraft:icon": {"texture": find_best_texture_match(safe_name, "items")},
        "minecraft:max_stack_size": max_stack,
    }
    if durability > 0:
        components["minecraft:durability"] = {"max_durability": durability}
    is_food = bool(re.search(r'FoodProperties|\.food\(|nutrition|saturation|isFood|extends\s+ItemFood|extends\s+BowlFoodItem', java_code, re.I))
    if is_food:
        nutrition = 4
        saturation = 0.3
        m3 = re.search(r'nutrition\s*\(?\s*(\d+)', java_code, re.I)
        if m3:
            nutrition = int(m3.group(1))
        m4 = re.search(r'saturation(?:Modifier)?\s*\(?\s*([0-9.]+)', java_code, re.I)
        if m4:
            saturation = float(m4.group(1))
        components["minecraft:food"] = {
            "nutrition": nutrition,
            "saturation_modifier": saturation,
            "can_always_eat": bool(re.search(r'alwaysEat|canAlwaysEat', java_code, re.I))
        }
        components["minecraft:use_animation"] = "eat"
        components["minecraft:use_duration"] = 32
    armor_slot = None
    if re.search(r'ArmorItem|EquipmentSlot\.HEAD', java_code, re.I):
        armor_slot = "slot.armor.head"
    elif re.search(r'EquipmentSlot\.CHEST', java_code, re.I):
        armor_slot = "slot.armor.chest"
    elif re.search(r'EquipmentSlot\.LEGS', java_code, re.I):
        armor_slot = "slot.armor.legs"
    elif re.search(r'EquipmentSlot\.FEET', java_code, re.I):
        armor_slot = "slot.armor.feet"
    if armor_slot:
        components["minecraft:wearable"] = {"protection": 3, "slot": armor_slot}
    if re.search(r'SwordItem|TieredItem|extends.*Sword', java_code, re.I):
        atk = 4.0
        m5 = re.search(r'attackDamage\s*[=+]+\s*([0-9.]+)', java_code, re.I)
        if m5:
            atk = float(m5.group(1))
        components["minecraft:damage"] = int(atk)
        components["minecraft:hand_equipped"] = True
    doc = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:item": {
            "description": {
                "identifier": item_id,
                "menu_category": {"category": "items"}
            },
            "components": components
        }
    }
    enchant_value = 0
    if re.search(r'EnchantmentCategory|getEnchantmentValue|enchantmentValue|enchantable', java_code, re.I):
        m_ench = re.search(r'(?:enchantmentValue|getEnchantmentValue)\s*\(\s*\)\s*\{\s*return\s*(\d+)', java_code, re.I)
        enchant_value = int(m_ench.group(1)) if m_ench else 10
    if enchant_value > 0:
        ench_slot = "all"
        if re.search(r'SwordItem|AxeItem|weapon', java_code, re.I):
            ench_slot = "weapon"
        elif re.search(r'ArmorItem|BootsItem|HelmItem|armor', java_code, re.I):
            ench_slot = "armor"
        elif re.search(r'PickaxeItem|ShovelItem|HoeItem|tool', java_code, re.I):
            ench_slot = "tool"
        components["minecraft:enchantable"] = {"value": enchant_value, "slot": ench_slot}
    if re.search(r'isFoil|hasGlint|isEnchanted', java_code, re.I):
        components["minecraft:glint"] = True
    has_instance_use = bool(re.search(
        r'@Override\s+public\s+\S+\s+(?:use|hurtEnemy|inventoryTick)\s*\(',
        java_code, re.DOTALL
    ))
    has_static_handlers = bool(_find_static_event_handlers(java_code))
    if has_instance_use or has_static_handlers:
        stub_written = generate_scripting_stub(java_code, safe_name, item_id, namespace)
        if stub_written and has_instance_use:
            components["minecraft:custom_components"] = [f"{namespace}:{safe_name}_use"]
    out_path = os.path.join(BP_FOLDER, "items", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    safe_write_json(out_path, doc)
    print(f"[item] Wrote {out_path}")
JAVA_PARTICLE_MAP = {
    "explosion": "minecraft:explosion_particle",
    "large_explosion": "minecraft:explosion_particle",
    "huge_explosion": "minecraft:explosion_particle",
    "fireworks_spark": "minecraft:fireworks_spark_particle",
    "bubble": "minecraft:bubble_particle",
    "splash": "minecraft:water_splash_particle",
    "wake": "minecraft:water_wake_particle",
    "suspended": "minecraft:water_splash_particle",
    "depth_suspend": "minecraft:water_splash_particle",
    "crit": "minecraft:critical_hit_emitter",
    "magic_crit": "minecraft:critical_hit_emitter",
    "smoke": "minecraft:basic_smoke_particle",
    "large_smoke": "minecraft:basic_smoke_particle",
    "mob_spell": "minecraft:spell_particle",
    "mob_spell_ambient": "minecraft:spell_particle",
    "spell": "minecraft:spell_particle",
    "instant_spell": "minecraft:spell_particle",
    "witch_magic": "minecraft:witch_spell_particle",
    "note": "minecraft:note_particle",
    "portal": "minecraft:portal_particle",
    "enchantment_table": "minecraft:enchanting_table_particle",
    "flame": "minecraft:basic_flame_particle",
    "lava": "minecraft:lava_particle",
    "footstep": "minecraft:falling_dust_sand_particle",
    "cloud": "minecraft:evaporation_particle",
    "reddust": "minecraft:redstone_wire_dust_particle",
    "snowball": "minecraft:snowball_particle",
    "drip_water": "minecraft:water_drip_particle",
    "drip_lava": "minecraft:lava_drip_particle",
    "snow_shovel": "minecraft:snowball_particle",
    "slime": "minecraft:slime_particle",
    "heart": "minecraft:heart_particle",
    "angry_villager": "minecraft:villager_angry_particle",
    "happy_villager": "minecraft:villager_happy_particle",
    "barrier": "minecraft:barrier_particle",
    "item_crack": "minecraft:basic_crit_particle",
    "block_crack": "minecraft:falling_dust_sand_particle",
    "block_dust": "minecraft:falling_dust_sand_particle",
    "droplet": "minecraft:water_drip_particle",
    "take": "minecraft:basic_crit_particle",
    "mob_appearance": "minecraft:elder_guardian_particle",
    "dragon_breath": "minecraft:dragon_breath_particle",
    "end_rod": "minecraft:end_rod_particle",
    "damage_indicator": "minecraft:critical_hit_emitter",
    "sweep_attack": "minecraft:critical_hit_emitter",
    "totem": "minecraft:totem_particle",
    "spit": "minecraft:llama_spit_particle",
    "squid_ink": "minecraft:squid_ink_particle",
    "bubble_pop": "minecraft:bubble_pop_particle",
    "current_down": "minecraft:bubble_particle",
    "bubble_column_up": "minecraft:bubble_particle",
    "nautilus": "minecraft:nautilus_particle",
    "dolphin": "minecraft:dolphin_particle",
    "campfire_cosy_smoke": "minecraft:campfire_smoke_particle",
    "campfire_signal_smoke": "minecraft:campfire_smoke_particle",
    "composter": "minecraft:composter_particle",
    "flash": "minecraft:flash_particle",
    "falling_lava": "minecraft:lava_drip_particle",
    "landing_lava": "minecraft:lava_particle",
    "falling_water": "minecraft:water_drip_particle",
    "dust": "minecraft:redstone_wire_dust_particle",
    "item_snowball": "minecraft:snowball_particle",
    "item_slime": "minecraft:slime_particle",
    "item_squid_ink": "minecraft:squid_ink_particle",
    "item_bubble_pop": "minecraft:bubble_pop_particle",
    "item_current_down": "minecraft:bubble_particle",
    "item_bubble_column_up": "minecraft:bubble_particle",
    "item_nautilus": "minecraft:nautilus_particle",
    "item_dolphin": "minecraft:dolphin_particle",
    "item_campfire_cosy_smoke": "minecraft:campfire_smoke_particle",
    "item_campfire_signal_smoke": "minecraft:campfire_smoke_particle",
    "item_composter": "minecraft:composter_particle",
    "item_flash": "minecraft:flash_particle",
    "item_falling_lava": "minecraft:lava_drip_particle",
    "item_landing_lava": "minecraft:lava_particle",
    "item_falling_water": "minecraft:water_drip_particle",
    "soul_fire_flame": "minecraft:soul_particle",
    "soul": "minecraft:soul_particle",
    "ash": "minecraft:basic_smoke_particle",
    "crimson_spore": "minecraft:crimson_spore_particle",
    "warped_spore": "minecraft:warped_spore_particle",
    "soul_fire_flame": "minecraft:soul_particle",
    "dripping_obsidian_tear": "minecraft:obsidian_tear_particle",
    "falling_obsidian_tear": "minecraft:obsidian_tear_particle",
    "landing_obsidian_tear": "minecraft:obsidian_tear_particle",
    "reverse_portal": "minecraft:portal_particle",
    "white_ash": "minecraft:basic_smoke_particle",
    "light": "minecraft:light_particle",
    "dust_color_transition": "minecraft:redstone_wire_dust_particle",
    "vibration": "minecraft:vibration_particle",
    "falling_spore_blossom": "minecraft:spore_blossom_particle",
    "spore_blossom_air": "minecraft:spore_blossom_particle",
    "small_flame": "minecraft:basic_flame_particle",
    "snowflake": "minecraft:snowball_particle",
    "dripping_dripstone_lava": "minecraft:lava_drip_particle",
    "falling_dripstone_lava": "minecraft:lava_drip_particle",
    "dripping_dripstone_water": "minecraft:water_drip_particle",
    "falling_dripstone_water": "minecraft:water_drip_particle",
    "glow_squid_ink": "minecraft:squid_ink_particle",
    "glow": "minecraft:glow_particle",
    "wax_on": "minecraft:wax_particle",
    "wax_off": "minecraft:wax_particle",
    "electric_spark": "minecraft:electric_spark_particle",
    "scrape": "minecraft:scrape_particle",
    "shriek": "minecraft:shriek_particle",
    "sonic_boom": "minecraft:sonic_boom_particle",
    "sculk_soul": "minecraft:soul_particle",
    "sculk_charge": "minecraft:sculk_charge_particle",
    "sculk_charge_pop": "minecraft:sculk_charge_pop_particle",
    "sonic_explosion": "minecraft:sonic_boom_particle",
    "dust_plume": "minecraft:dust_plume_particle",
    "gust": "minecraft:gust_particle",
    "trial_spawner_detection": "minecraft:trial_spawner_detection_particle",
    "trial_spawner_detection_ominous": "minecraft:trial_spawner_detection_ominous_particle",
    "vault_connection": "minecraft:vault_connection_particle",
    "dust_pillar": "minecraft:dust_pillar_particle",
    "ominous_spawning": "minecraft:ominous_spawning_particle",
    "raid_omen": "minecraft:raid_omen_particle",
    "trial_omen": "minecraft:trial_omen_particle",
}
def extract_and_generate_particles(java_code: str, entity_id: str, namespace: str):
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    found = set()

    particle_refs = re.findall(r'\b(\w+)\s*\.\s*spawn\s*\(', java_code)                         
    for ref in particle_refs:
        if ref in JAVA_PARTICLE_MAP:
            found.add((ref, JAVA_PARTICLE_MAP[ref]))
        else:

            found.add((ref, "minecraft:enchantment_table_particle"))                     
    if not found:
        return
    out_dir = os.path.join(RP_FOLDER, "particles")
    os.makedirs(out_dir, exist_ok=True)
    for java_name, bedrock_ref in found:
        particle_id = f"{namespace}:{safe_name}_{java_name}"
        doc = {
            "format_version": "1.10.0",
            "particle_effect": {
                "description": {
                    "identifier": particle_id,
                    "basic_render_parameters": {
                        "material": "particles_alpha",
                        "texture": "textures/particle/particles"
                    }
                },
                "components": {
                    "minecraft:emitter_rate_instant": {"num_particles": 8},
                    "minecraft:emitter_lifetime_once": {"active_time": 0.5},
                    "minecraft:particle_initial_speed": 1.0,
                    "minecraft:particle_lifetime_expression": {"max_lifetime": 0.5},
                    "minecraft:particle_appearance_billboard": {
                        "size": [0.1, 0.1],
                        "facing_camera_type": "lookat_xyz",
                        "uv": {"texture_width": 128, "texture_height": 128, "uv": [0, 0], "uv_size": [8, 8]}
                    }
                },
                "_note": f"stub converted from Java particle: {java_name} (original ref: {bedrock_ref})"
            }
        }
        out_path = os.path.join(out_dir, f"{safe_name}_{java_name}.json")
        safe_write_json(out_path, doc)
    print(f"[particles] Wrote {len(found)} particle stubs for {entity_id}")
def convert_lang_files():
    lang_dir = os.path.join(RP_FOLDER, "lang")
    if not os.path.isdir(lang_dir):
        return
    for fname in os.listdir(lang_dir):
        fpath = os.path.join(lang_dir, fname)
        if fname.endswith(".json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                lang_name = os.path.splitext(fname)[0]
                parts = lang_name.split("_")
                if len(parts) == 2:
                    lang_name = f"{parts[0]}_{parts[1].upper()}"
                out_path = os.path.join(lang_dir, f"{lang_name}.lang")
                lines = []
                for k, v in data.items():
                    safe_v = str(v).replace("\n", "\\n")
                    lines.append(f"{k}={safe_v}")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                os.remove(fpath)
                print(f"[lang] Converted {fname} -> {lang_name}.lang ({len(lines)} entries)")
            except Exception as e:
                print(f"[lang] Failed to convert {fname}: {e}")
JAVA_RECIPE_ITEM_MAP = {
    "minecraft:crafting_table": "minecraft:crafting_table",
    "minecraft:furnace": "minecraft:furnace",
    "minecraft:smithing_table": "minecraft:smithing_table",
}
def convert_java_recipe(recipe_data: dict, namespace: str) -> Optional[dict]:
    rtype = recipe_data.get("type", "")
    if "crafting_shaped" in rtype:
        pattern = recipe_data.get("pattern", [])
        key_map = recipe_data.get("key", {})
        result = recipe_data.get("result", {})
        result_item = result.get("item", result) if isinstance(result, dict) else result
        if ":" in str(result_item):
            ns, itm = str(result_item).split(":", 1)
            if ns != "minecraft":
                result_item = f"{namespace}:{sanitize_identifier(itm)}"
        count = result.get("count", 1) if isinstance(result, dict) else 1
        bedrock_key = {}
        for char, ingredient in key_map.items():
            item = ingredient.get("item", "") if isinstance(ingredient, dict) else ingredient
            if isinstance(item, list):
                item = item[0].get("item", "") if item else ""
            bedrock_key[char] = {"item": item}
        return {
            "format_version": "1.21.0",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{sanitize_identifier(str(result_item).split(':')[-1])}_shaped"},
                "tags": ["crafting_table"],
                "pattern": pattern,
                "key": bedrock_key,
                "result": {"item": result_item, "count": count}
            }
        }
    elif "crafting_shapeless" in rtype:
        ingredients = recipe_data.get("ingredients", [])
        result = recipe_data.get("result", {})
        result_item = result.get("item", result) if isinstance(result, dict) else result
        if ":" in str(result_item):
            ns, itm = str(result_item).split(":", 1)
            if ns != "minecraft":
                result_item = f"{namespace}:{sanitize_identifier(itm)}"
        count = result.get("count", 1) if isinstance(result, dict) else 1
        bedrock_ingredients = []
        for ing in ingredients:
            item = ing.get("item", "") if isinstance(ing, dict) else ing
            if isinstance(item, list):
                item = item[0].get("item", "") if item else ""
            bedrock_ingredients.append({"item": item})
        return {
            "format_version": "1.21.0",
            "minecraft:recipe_shapeless": {
                "description": {"identifier": f"{namespace}:{sanitize_identifier(str(result_item).split(':')[-1])}_shapeless"},
                "tags": ["crafting_table"],
                "ingredients": bedrock_ingredients,
                "result": {"item": result_item, "count": count}
            }
        }
    elif "smelting" in rtype or "smoking" in rtype or "blasting" in rtype:
        ingredient = recipe_data.get("ingredient", {})
        item = ingredient.get("item", "") if isinstance(ingredient, dict) else ingredient
        result = recipe_data.get("result", "")
        if ":" in str(result):
            ns, itm = str(result).split(":", 1)
            if ns != "minecraft":
                result = f"{namespace}:{sanitize_identifier(itm)}"
        cook_time = recipe_data.get("cookingtime", 200) / 20
        return {
            "format_version": "1.21.0",
            "minecraft:recipe_furnace": {
                "description": {"identifier": f"{namespace}:{sanitize_identifier(str(result).split(':')[-1])}_furnace"},
                "tags": ["furnace", "smoker", "blast_furnace"],
                "input": {"item": item},
                "output": str(result)
            }
        }
    return None
def process_recipes_from_jar(jar_path: str, namespace: str):
    out_base = os.path.join(BP_FOLDER, "recipes")
    os.makedirs(out_base, exist_ok=True)
    count = 0
    with zipfile.ZipFile(jar_path, "r") as jar:
        for name in jar.namelist():
            lower = name.lower()
            if "/recipes/" not in lower or not lower.endswith(".json"):
                continue
            try:
                with jar.open(name) as f:
                    data = json.loads(f.read().decode("utf-8"))
                bedrock = convert_java_recipe(data, namespace)
                if not bedrock:
                    continue
                fname = sanitize_filename_keep_ext(os.path.basename(name))
                out_path = os.path.join(out_base, fname)
                safe_write_json(out_path, bedrock)
                count += 1
            except Exception as e:
                print(f"[recipe] Failed to convert {name}: {e}")
    print(f"[recipe] Converted {count} recipes -> {out_base}")
def _categorise_animations(animations: set) -> dict:
    buckets = {
        "idle":    [], "walk":   [], "run":    [], "attack": [],
        "hurt":    [], "death":  [], "sit":    [], "swim":   [],
        "fly":     [], "sleep":  [], "spawn":  [], "other":  [],
    }
    KEYWORDS = {
        "idle":   ("idle", "stand", "pose", "float"),
        "walk":   ("walk",),
        "run":    ("run", "chase", "sprint"),
        "attack": ("attack", "strike", "bite", "swipe", "slam", "lunge", "claw"),
        "hurt":   ("hurt", "hit", "flinch", "pain"),
        "death":  ("death", "die", "dying", "dead"),
        "sit":    ("sit", "sitting", "crouch", "lay"),
        "swim":   ("swim", "swimming"),
        "fly":    ("fly", "flying", "hover", "glide"),
        "sleep":  ("sleep", "sleeping", "rest"),
        "spawn":  ("spawn", "appear", "emerge", "summon"),
    }
    for anim in animations:
        a = anim.lower()
        placed = False
        for bucket, keys in KEYWORDS.items():
            if any(k in a for k in keys):
                buckets[bucket].append(anim)
                placed = True
                break
        if not placed:
            buckets["other"].append(anim)
    return buckets
def generate_animation_controller(entity_id: str, animations: set, namespace: str,
                                   ai_goals: list = None, java_code: str = "") -> Optional[str]:
    if not animations:
        return None
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    controller_id = f"controller.animation.{namespace}.{safe_name}"
    buckets = _categorise_animations(animations)
    ai_goals = ai_goals or []
    has_walk   = bool(buckets["walk"] or buckets["run"])
    has_attack = bool(buckets["attack"])
    has_hurt   = bool(buckets["hurt"])
    has_death  = bool(buckets["death"])
    has_sit    = bool(buckets["sit"])
    has_swim   = bool(buckets["swim"])
    has_fly    = bool(buckets["fly"])
    has_sleep  = bool(buckets["sleep"])
    has_spawn  = bool(buckets["spawn"])
    def pick(bucket): return buckets[bucket][0] if buckets[bucket] else None
    idle_anim   = pick("idle")
    walk_anim   = pick("walk") or pick("run")
    run_anim    = pick("run") or walk_anim
    attack_anim = pick("attack")
    hurt_anim   = pick("hurt")
    death_anim  = pick("death")
    sit_anim    = pick("sit")
    swim_anim   = pick("swim")
    fly_anim    = pick("fly")
    sleep_anim  = pick("sleep")
    spawn_anim  = pick("spawn")
    if not idle_anim:
        idle_anim = sorted(animations)[0]
    states = {}
    if has_spawn:
        states["spawn"] = {
            "animations": [spawn_anim],
            "transitions": [{"default": f"query.anim_time >= 1.0"}]
        }
    default_transitions = []
    if has_spawn:
        pass
    if has_walk:
        default_transitions.append({"moving": "query.modified_move_speed > 0.1"})
    if has_attack:
        default_transitions.append({"attacking": "query.is_attacking"})
    if has_hurt:
        default_transitions.append({"hurt": "query.is_hurt"})
    if has_death:
        default_transitions.append({"death": "query.health <= 0"})
    if has_sit and "SitWhenOrderedToGoal" in ai_goals:
        default_transitions.append({"sitting": "query.is_sitting"})
    if has_sleep:
        default_transitions.append({"sleeping": "query.is_sleeping"})
    default_state = {"animations": [idle_anim]}
    if default_transitions:
        default_state["transitions"] = default_transitions
    states["default"] = default_state
    if has_walk:
        moving_anim = run_anim if run_anim else walk_anim
        if buckets["walk"] and buckets["run"]:
            moving_anims = [
                {walk_anim: "1.0 - math.min(query.modified_move_speed / 0.3, 1.0)"},
                {run_anim:  "math.min(query.modified_move_speed / 0.3, 1.0)"}
            ]
        else:
            moving_anims = [moving_anim]
        moving_transitions = [{"default": "query.modified_move_speed <= 0.1"}]
        if has_attack:
            moving_transitions.append({"attacking": "query.is_attacking"})
        if has_death:
            moving_transitions.append({"death": "query.health <= 0"})
        states["moving"] = {
            "animations": moving_anims,
            "transitions": moving_transitions
        }
    if has_attack:
        attack_transitions = [{"default": "!query.is_attacking"}]
        if has_death:
            attack_transitions.append({"death": "query.health <= 0"})
        states["attacking"] = {
            "animations": [attack_anim],
            "transitions": attack_transitions
        }
    if has_hurt:
        states["hurt"] = {
            "animations": [hurt_anim],
            "transitions": [
                {"death": "query.health <= 0"},
                {"default": f"query.anim_time >= 0.3"}
            ]
        }
    if has_death:
        states["death"] = {
            "animations": [death_anim],
            "transitions": []
        }
    if has_sit:
        states["sitting"] = {
            "animations": [sit_anim],
            "transitions": [{"default": "!query.is_sitting"}]
        }
    if has_swim:
        swim_transitions = [{"default": "!query.is_in_water"}]
        if has_attack:
            swim_transitions.insert(0, {"attacking": "query.is_attacking"})
        states["swimming"] = {
            "animations": [swim_anim],
            "transitions": swim_transitions
        }
        if "default" in states and "transitions" in states["default"]:
            states["default"]["transitions"].insert(0, {"swimming": "query.is_in_water"})
        if "moving" in states:
            states["moving"]["transitions"].insert(0, {"swimming": "query.is_in_water"})
    if has_fly:
        states["flying"] = {
            "animations": [fly_anim],
            "transitions": [{"default": "query.is_on_ground"}]
        }
        if "default" in states and "transitions" in states["default"]:
            states["default"]["transitions"].insert(0, {"flying": "!query.is_on_ground"})
    if has_sleep:
        states["sleeping"] = {
            "animations": [sleep_anim],
            "transitions": [{"default": "!query.is_sleeping"}]
        }
    for anim in buckets["other"]:
        state_name = sanitize_identifier(anim.split(".")[-1])
        if state_name not in states and state_name != "default":
            if "animations" in states.get("default", {}):
                if isinstance(states["default"]["animations"], list):
                    states["default"]["animations"].append(anim)
    initial = "spawn" if has_spawn else "default"
    doc = {
        "format_version": "1.10.0",
        "animation_controllers": {
            controller_id: {
                "initial_state": initial,
                "states": states
            }
        }
    }
    out_dir = os.path.join(RP_FOLDER, "animation_controllers")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{safe_name}.animation_controllers.json")
    safe_write_json(out_path, doc)
    print(f"[anim_ctrl] Wrote {out_path} ({len(states)} states)")
    return controller_id
def patch_rp_entity_with_controller(entity_basename: str, animations: set,
                                     controller_id: Optional[str], namespace: str):
    rp_path = os.path.join(RP_FOLDER, "entity", f"{entity_basename}.entity.json")
    if not os.path.exists(rp_path):
        return
    try:
        with open(rp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    desc = data.get("minecraft:client_entity", {}).get("description", {})
    if not desc:
        return
    buckets = _categorise_animations(animations)
    anim_map: Dict[str, str] = {}
    def add_anim(key: str, anim_id: str):
        if anim_id and anim_id not in anim_map.values():
            anim_map[key] = anim_id
    for b_name in ("idle", "walk", "run", "attack", "hurt", "death",
                   "sit", "swim", "fly", "sleep", "spawn"):
        if buckets[b_name]:
            add_anim(b_name, buckets[b_name][0])
    for i, anim in enumerate(buckets["other"]):
        add_anim(f"anim_{i}", anim)
    if anim_map:
        desc["animations"] = anim_map
    animate_list = []
    if controller_id:
        ctrl_short = "ctrl"
        if "animations" not in desc:
            desc["animations"] = {}
        desc["animations"][ctrl_short] = controller_id
        desc["animation_controllers"] = [ctrl_short]
        animate_list = [ctrl_short]
        if "idle" in anim_map:
            animate_list.append({"idle": "query.is_alive"})
        desc["scripts"] = {"animate": animate_list}
    elif anim_map:
        passive = []
        for short, full_id in anim_map.items():
            loop_names = ("idle", "walk", "run", "swim", "fly")
            if any(n in short for n in loop_names):
                passive.append({short: "query.is_alive"})
            else:
                passive.append(short)
        desc["scripts"] = {"animate": passive or list(anim_map.keys())}
    try:
        with open(rp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[anim_wire] Patched {os.path.basename(rp_path)}: "
              f"{len(anim_map)} anim(s)"
              f"{', controller wired as ' + repr('ctrl') if controller_id else ''}")
    except Exception as e:
        print(f"[anim_wire] Failed to patch {rp_path}: {e}")
def run_validation_pass() -> list:
    warnings = []
    tex_dir = os.path.join(RP_FOLDER, "textures")
    tex_on_disk = set()
    if os.path.isdir(tex_dir):
        for root, _, files in os.walk(tex_dir):
            for f in files:
                if f.lower().endswith(".png"):
                    rel = os.path.relpath(os.path.join(root, f), RP_FOLDER).replace("\\", "/")
                    tex_on_disk.add(rel)
                    tex_on_disk.add(os.path.splitext(rel)[0])
    geo_dir = os.path.join(RP_FOLDER, "geometry")
    geo_on_disk = set()
    if os.path.isdir(geo_dir):
        for f in os.listdir(geo_dir):
            geo_on_disk.add(os.path.splitext(f)[0].lower())
    anim_dir = os.path.join(RP_FOLDER, "animations")
    anim_on_disk = set()
    if os.path.isdir(anim_dir):
        for f in os.listdir(anim_dir):
            anim_on_disk.add(os.path.splitext(f)[0].lower())
    entity_dir = os.path.join(RP_FOLDER, "entity")
    if os.path.isdir(entity_dir):
        for fname in os.listdir(entity_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(entity_dir, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                desc = data.get("minecraft:client_entity", {}).get("description", {})
                for tex_key, tex_path in desc.get("textures", {}).items():
                    full = tex_path if tex_path.startswith("textures/") else f"textures/{tex_path}"
                    if full not in tex_on_disk and tex_path not in tex_on_disk:
                        warnings.append(f"[WARN] Missing texture '{tex_path}' referenced in {fname}")
                for geo_key, geo_id in desc.get("geometry", {}).items():
                    if geo_id.startswith("geometry."):
                        geo_tail = sanitize_identifier(geo_id[len("geometry."):])
                    else:
                        geo_tail = sanitize_identifier(geo_id)
                    geo_last = geo_tail.split(".")[-1] if "." in geo_tail else geo_tail
                    if (geo_tail not in geo_on_disk and geo_last not in geo_on_disk):
                        warnings.append(
                            f"[WARN] Geometry '{geo_id}' in {fname} has no matching .geo.json "
                            f"(placeholder — add the geometry file to fix rendering)"
                        )
                for anim_key, anim_id in desc.get("animations", {}).items():
                    anim_base = sanitize_identifier(anim_id.split(".")[-2]) if "." in anim_id else anim_id
                    if not anim_on_disk:
                        warnings.append(f"[WARN] Animation '{anim_id}' referenced in {fname} but no animation files found")
                        break
            except Exception as e:
                warnings.append(f"[WARN] Could not parse {fname}: {e}")
    bp_entity_dir = os.path.join(BP_FOLDER, "entities")
    if os.path.isdir(bp_entity_dir):
        for fname in os.listdir(bp_entity_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(bp_entity_dir, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                comps = data.get("minecraft:entity", {}).get("components", {})
                loot = comps.get("minecraft:loot", {}).get("table", "")
                if loot:
                    loot_full = os.path.join(BP_FOLDER, loot)
                    if not os.path.exists(loot_full):
                        warnings.append(f"[WARN] Loot table '{loot}' referenced in {fname} does not exist")
            except Exception:
                pass
    return warnings
ENTITY_REGISTRY: Dict[str, str] = {}
ATTRS_REGISTRY:  Dict[str, dict] = {}
SOUND_CONST_MAP: Dict[str, str] = {}
def detect_mod_id(java_files: dict) -> str:
    for path, code in java_files.items():
        ast = JavaAST(code)
        ast._parse()
        if ast._tree is not None:
            val = ast.annotation_value('Mod')
            if val and re.match(r'^[a-z0-9_-]+$', val):
                return sanitize_identifier(val)
            vals = ast.field_string_values({'MOD_ID', 'MODID', 'MOD_ID_STR', 'ID'})
            for _, v in vals.items():
                if v and re.match(r'^[a-z0-9_-]+$', v):
                    return sanitize_identifier(v)
        else:
            m = re.search(r'@Mod\s*\(\s*["\'\']([a-z0-9_-]+)["\'\']', code)
            if m:
                return sanitize_identifier(m.group(1))
            m = re.search(r'(?:MOD_ID|MODID|MOD_ID_STR|ID)\s*=\s*["\']([a-z0-9_-]+)["\']', code)
            if m:
                return sanitize_identifier(m.group(1))
    for root, _, files in os.walk("."):
        for f in files:
            if f == "neoforge.mods.toml":
                try:
                    c = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                    m = re.search(r'modId\s*=\s*["\']([a-z0-9_-]+)["\']', c)
                    if m:
                        print(f"[detect_mod_id] Found NeoForge mod ID in {f}: {m.group(1)!r}")
                        return sanitize_identifier(m.group(1))
                except Exception:
                    pass
            if f == "mods.toml":
                try:
                    c = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                    m = re.search(r'modId\s*=\s*["\']([a-z0-9_-]+)["\']', c)
                    if m:
                        return sanitize_identifier(m.group(1))
                except Exception:
                    pass
            if f == "fabric.mod.json":
                try:
                    data = json.load(open(os.path.join(root, f), encoding="utf-8"))
                    if "id" in data:
                        return sanitize_identifier(data["id"])
                except Exception:
                    pass
            if f == "quilt.mod.json":
                try:
                    data = json.load(open(os.path.join(root, f), encoding="utf-8"))
                    qm = data.get("quilt_loader", {})
                    if "id" in qm:
                        return sanitize_identifier(qm["id"])
                except Exception:
                    pass
            if f in ("build.gradle", "build.gradle.kts"):
                try:
                    c = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                    for pat in [
                        r'archivesBaseName\s*=\s*["\']([a-z0-9_-]+)["\']',
                        r'mod_id\s*=\s*["\']([a-z0-9_-]+)["\']',
                        r'modId\s*[=:]\s*["\']([a-z0-9_-]+)["\']',
                    ]:
                        m = re.search(pat, c, re.I)
                        if m:
                            candidate = sanitize_identifier(m.group(1))
                            if candidate and len(candidate) >= 2:
                                print(f"[detect_mod_id] Found mod ID in {f}: {candidate!r}")
                                return candidate
                except Exception:
                    pass
            if f == "gradle.properties":
                try:
                    c = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                    for pat in [
                        r'mod_id\s*=\s*([a-z0-9_-]+)',
                        r'modId\s*=\s*([a-z0-9_-]+)',
                        r'archivesBaseName\s*=\s*([a-z0-9_-]+)',
                    ]:
                        m = re.search(pat, c, re.I)
                        if m:
                            candidate = sanitize_identifier(m.group(1).strip())
                            if candidate and len(candidate) >= 2:
                                return candidate
                except Exception:
                    pass
    return ""
def _build_resource_location_constants(java_files: dict) -> Dict[str, str]:
    constants: Dict[str, str] = {}
    _RL_TYPES = r'(?:ResourceLocation|RL|Identifier)'
    for _path, code in java_files.items():
        for m in re.finditer(
            rf'(?:static\s+final\s+)?{_RL_TYPES}\s+(\w+)\s*='
            r'\s*new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
            code
        ):
            constants[m.group(1)] = f"{m.group(2)}:{m.group(3)}"
        for m in re.finditer(
            rf'(?:static\s+final\s+)?{_RL_TYPES}\s+(\w+)\s*='
            r'\s*new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_:/-][^"\']*)["\']',
            code
        ):
            constants[m.group(1)] = m.group(2)
        for m in re.finditer(
            rf'(?:static\s+final\s+)?{_RL_TYPES}\s+(\w+)\s*='
            r'\s*ResourceLocation\.(?:fromNamespaceAndPath|of)\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
            code
        ):
            constants[m.group(1)] = f"{m.group(2)}:{m.group(3)}"
        for m in re.finditer(
            rf'(?:static\s+final\s+)?{_RL_TYPES}\s+(\w+)\s*='
            r'\s*ResourceLocation\.(?:tryParse|tryBuild|of)\s*\(\s*["\']([a-z0-9_:/-][^"\']*)["\']',
            code
        ):
            constants[m.group(1)] = m.group(2)
    return constants
def build_entity_registry(java_files: dict, namespace: str) -> dict:
    registry = {}
    for path, code in java_files.items():
        ast = JavaAST(code)
        ast._parse()
        if ast._tree is not None:
            for inv in ast.invocations_of('register'):
                args = getattr(inv, 'arguments', []) or []
                if not args:
                    continue
                if isinstance(args[0], javalang.tree.Literal):
                    reg_name = args[0].value.strip('"').strip("'")
                    if not re.match(r'^[a-z0-9_]+$', reg_name):
                        continue
                    for arg in args[1:]:
                        if isinstance(arg, javalang.tree.MethodReference):
                            cls_ref = getattr(arg.expression, 'member', None) or getattr(arg.expression, 'name', None)
                            if cls_ref and cls_ref not in ('super', 'this') and len(cls_ref) > 2:
                                registry[cls_ref] = f"{namespace}:{reg_name}"
            cls_name = ast.primary_class_name()
            if cls_name:
                for inv in ast.invocations_of('setRegistryName'):
                    raw = JavaAST.first_string_arg(inv)
                    if raw:
                        registry[cls_name] = raw if ':' in raw else f"{namespace}:{raw}"
                        break
        for m in re.finditer(
            r'RegistryObject<EntityType<([A-Za-z0-9_]+)>>\s+\w+\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_]+)["\']',
            code):
            registry[m.group(1)] = f"{namespace}:{m.group(2)}"
        for m in re.finditer(
            r'(?:DeferredHolder|DeferredEntity|Supplier)<[^>]*EntityType<([A-Za-z0-9_]+)>[^>]*>\s+\w+\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_]+)["\']',
            code):
            registry[m.group(1)] = f"{namespace}:{m.group(2)}"
        for m in re.finditer(
            r'\.register\s*\(\s*["\']([a-z0-9_]+)["\']\s*,[^;]*?([A-Za-z0-9_]+)::new',
            code, re.DOTALL):
            cls = m.group(2)
            if cls not in ("super", "this") and len(cls) > 2:
                registry[cls] = f"{namespace}:{m.group(1)}"
        for m in re.finditer(
            r'EntityType\.Builder[^;]*\.of\s*\(\s*([A-Za-z0-9_]+)::new[^;]*\.build\s*\(\s*["\']([a-z0-9_]+)["\']',
            code, re.DOTALL):
            registry[m.group(1)] = f"{namespace}:{m.group(2)}"
        cls_name = extract_class_name(code)
        if cls_name:
            m = re.search(r'setRegistryName\s*\(\s*["\']([a-z0-9_:-]+)["\']', code)
            if m:
                raw = m.group(1)
                registry[cls_name] = raw if ":" in raw else f"{namespace}:{raw}"
    rl_constants = _build_resource_location_constants(java_files)
    if rl_constants:
        for _path2, code2 in java_files.items():
            for m in re.finditer(
                r'\.register\s*\(\s*([A-Z_][A-Z0-9_]{2,})\s*,'
                r'\s*(?:([A-Za-z0-9_]+)::new|\(\)\s*->\s*new\s+([A-Za-z0-9_]+)\s*\()',
                code2
            ):
                const_name = m.group(1)
                cls = m.group(2) or m.group(3)
                if const_name in rl_constants and cls and cls not in ('super', 'this', 'EntityType'):
                    rl = rl_constants[const_name]
                    if ':' in rl and cls not in registry:
                        registry[cls] = rl
            for m in re.finditer(
                r'EntityType\.Builder[^;]*\.of\s*\(\s*([A-Za-z0-9_]+)::new[^;]*\.build\s*\(\s*([A-Z_][A-Z0-9_]{2,})\s*\)',
                code2, re.DOTALL
            ):
                cls = m.group(1)
                const_name = m.group(2)
                if const_name in rl_constants and cls and cls not in registry:
                    rl = rl_constants[const_name]
                    if ':' in rl:
                        registry[cls] = rl
            for m in re.finditer(
                r'\.register\s*\(\s*["\']([a-z0-9_]+)["\']\s*,[^;]*?\.build\s*\(\s*([A-Z_][A-Z0-9_]{2,})\s*\)',
                code2, re.DOTALL
            ):
                reg_name = m.group(1)
                const_name = m.group(2)
                if const_name in rl_constants:
                    rl = rl_constants[const_name]
                    ns_part = rl.split(':')[0] if ':' in rl else namespace
                    nearby = code2[max(0, m.start()-300):m.end()]
                    cm = re.search(r'([A-Za-z0-9_]+)::new', nearby)
                    if cm:
                        cls = cm.group(1)
                        if cls not in ('super', 'this', 'EntityType') and cls not in registry:
                            registry[cls] = f"{ns_part}:{reg_name}"
    return registry
def build_attributes_registry(java_files: dict) -> dict:
    attrs_reg = {}
    defaults = {"health":20.0,"attack_damage":3.0,"movement_speed":0.3,
                "follow_range":16.0,"knockback_resistance":0.0,"armor":0.0}
    for path, code in java_files.items():
        if not re.search(
            r'(?:createAttributes|getDefaultAttributes|createMobAttributes'
            r'|createMonsterAttributes|createAnimalAttributes|createLivingAttributes)',
            code
        ):
            continue
        cls_name = extract_class_name(code)
        if not cls_name: continue
        attrs = extract_attributes_from_java(code)
        if any(attrs.get(k) != defaults.get(k) for k in defaults):
            attrs_reg[cls_name] = attrs
    return attrs_reg
def build_sound_registry_from_java(java_files: dict, namespace: str) -> dict:
    sound_map = {}
    for path, code in java_files.items():
        fname = os.path.basename(path).lower()
        if not (any(k in fname for k in ("sound","sounds","sfx","audio")) or
                ("SoundEvent" in code and "register" in code)):
            continue
        for m in re.finditer(
            r'(?:RegistryObject<SoundEvent>|SoundEvent)\s+([A-Z_0-9]+)\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_.]+)["\']',
            code):
            sound_map[m.group(1)] = sanitize_sound_key(f"{namespace}.{m.group(2)}")
        for m in re.finditer(
            r'(?:DeferredHolder<SoundEvent[^>]*>|Supplier<SoundEvent>)\s+([A-Z_0-9]+)\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_.]+)["\']',
            code):
            sound_map[m.group(1)] = sanitize_sound_key(f"{namespace}.{m.group(2)}")
        for m in re.finditer(
            r'([A-Z_0-9]{3,})\s*=\s*(?:SoundEvent\.create[^(]*|Registry\.register[^(]*)\([^)]*["\']([a-z0-9_.:-]+)["\']',
            code):
            sid = m.group(2)
            if ":" in sid: sid = sid.split(":",1)[1]
            sound_map[m.group(1)] = sanitize_sound_key(f"{namespace}.{sid}")
    return sound_map
def run_prescan(java_files: dict, namespace: str) -> str:
    global ENTITY_REGISTRY, ATTRS_REGISTRY, SOUND_CONST_MAP
    detected = detect_mod_id(java_files)
    ns = detected or namespace
    build_inheritance_graph(java_files)
    ENTITY_REGISTRY = build_entity_registry(java_files, ns)
    ATTRS_REGISTRY  = build_attributes_registry(java_files)
    SOUND_CONST_MAP = build_sound_registry_from_java(java_files, ns)
    build_goal_inheritance_map(java_files)
    print(f"[prescan] mod_id={ns!r} | entities={len(ENTITY_REGISTRY)} | "
          f"attr_classes={len(ATTRS_REGISTRY)} | sounds={len(SOUND_CONST_MAP)} | "
          f"inheritance_graph={len(_INHERITANCE_GRAPH)}")
    for cls, eid in list(ENTITY_REGISTRY.items())[:6]:
        print(f"  {cls} -> {eid}")
    return ns
JAVA_TO_BEDROCK_BLOCK = {
    "minecraft:air": "minecraft:air",
    "minecraft:cave_air": "minecraft:air",
    "minecraft:void_air": "minecraft:air",
    "minecraft:stone": "minecraft:stone",
    "minecraft:granite": "minecraft:stone",
    "minecraft:polished_granite": "minecraft:stone",
    "minecraft:diorite": "minecraft:stone",
    "minecraft:polished_diorite": "minecraft:stone",
    "minecraft:andesite": "minecraft:stone",
    "minecraft:polished_andesite": "minecraft:stone",
    "minecraft:cobblestone": "minecraft:cobblestone",
    "minecraft:mossy_cobblestone": "minecraft:mossy_cobblestone",
    "minecraft:stone_bricks": "minecraft:stonebrick",
    "minecraft:mossy_stone_bricks": "minecraft:stonebrick",
    "minecraft:cracked_stone_bricks": "minecraft:stonebrick",
    "minecraft:chiseled_stone_bricks": "minecraft:stonebrick",
    "minecraft:infested_stone": "minecraft:stone",
    "minecraft:gravel": "minecraft:gravel",
    "minecraft:sand": "minecraft:sand",
    "minecraft:red_sand": "minecraft:sand",
    "minecraft:sandstone": "minecraft:sandstone",
    "minecraft:smooth_sandstone": "minecraft:sandstone",
    "minecraft:chiseled_sandstone": "minecraft:sandstone",
    "minecraft:red_sandstone": "minecraft:red_sandstone",
    "minecraft:dirt": "minecraft:dirt",
    "minecraft:coarse_dirt": "minecraft:dirt",
    "minecraft:podzol": "minecraft:podzol",
    "minecraft:grass_block": "minecraft:grass",
    "minecraft:mycelium": "minecraft:mycelium",
    "minecraft:oak_log": "minecraft:log",
    "minecraft:spruce_log": "minecraft:log",
    "minecraft:birch_log": "minecraft:log",
    "minecraft:jungle_log": "minecraft:log",
    "minecraft:acacia_log": "minecraft:log2",
    "minecraft:dark_oak_log": "minecraft:log2",
    "minecraft:oak_planks": "minecraft:planks",
    "minecraft:spruce_planks": "minecraft:planks",
    "minecraft:birch_planks": "minecraft:planks",
    "minecraft:jungle_planks": "minecraft:planks",
    "minecraft:acacia_planks": "minecraft:planks",
    "minecraft:dark_oak_planks": "minecraft:planks",
    "minecraft:oak_leaves": "minecraft:leaves",
    "minecraft:spruce_leaves": "minecraft:leaves",
    "minecraft:birch_leaves": "minecraft:leaves",
    "minecraft:jungle_leaves": "minecraft:leaves",
    "minecraft:acacia_leaves": "minecraft:leaves2",
    "minecraft:dark_oak_leaves": "minecraft:leaves2",
    "minecraft:coal_ore": "minecraft:coal_ore",
    "minecraft:iron_ore": "minecraft:iron_ore",
    "minecraft:gold_ore": "minecraft:gold_ore",
    "minecraft:diamond_ore": "minecraft:diamond_ore",
    "minecraft:emerald_ore": "minecraft:emerald_ore",
    "minecraft:lapis_ore": "minecraft:lapis_ore",
    "minecraft:redstone_ore": "minecraft:redstone_ore",
    "minecraft:nether_quartz_ore": "minecraft:quartz_ore",
    "minecraft:bricks": "minecraft:brick_block",
    "minecraft:nether_bricks": "minecraft:nether_brick",
    "minecraft:red_nether_bricks": "minecraft:red_nether_brick",
    "minecraft:obsidian": "minecraft:obsidian",
    "minecraft:bedrock": "minecraft:bedrock",
    "minecraft:water": "minecraft:water",
    "minecraft:lava": "minecraft:lava",
    "minecraft:glass": "minecraft:glass",
    "minecraft:glowstone": "minecraft:glowstone",
    "minecraft:netherrack": "minecraft:netherrack",
    "minecraft:soul_sand": "minecraft:soul_sand",
    "minecraft:soul_soil": "minecraft:soul_sand",
    "minecraft:magma_block": "minecraft:magma",
    "minecraft:ice": "minecraft:ice",
    "minecraft:packed_ice": "minecraft:packed_ice",
    "minecraft:snow_block": "minecraft:snow",
    "minecraft:clay": "minecraft:clay",
    "minecraft:terracotta": "minecraft:hardened_clay",
    "minecraft:white_terracotta": "minecraft:stained_hardened_clay",
    "minecraft:chest": "minecraft:chest",
    "minecraft:trapped_chest": "minecraft:trapped_chest",
    "minecraft:crafting_table": "minecraft:crafting_table",
    "minecraft:furnace": "minecraft:furnace",
    "minecraft:bookshelf": "minecraft:bookshelf",
    "minecraft:spawner": "minecraft:mob_spawner",
    "minecraft:tnt": "minecraft:tnt",
    "minecraft:torch": "minecraft:torch",
    "minecraft:wall_torch": "minecraft:torch",
    "minecraft:ladder": "minecraft:ladder",
    "minecraft:iron_bars": "minecraft:iron_bars",
    "minecraft:glass_pane": "minecraft:glass_pane",
    "minecraft:vine": "minecraft:vine",
    "minecraft:cobweb": "minecraft:web",
    "minecraft:hay_block": "minecraft:hay_block",
    "minecraft:sponge": "minecraft:sponge",
    "minecraft:prismarine": "minecraft:prismarine",
    "minecraft:sea_lantern": "minecraft:sea_lantern",
    "minecraft:dark_prismarine": "minecraft:prismarine",
    "minecraft:prismarine_bricks": "minecraft:prismarine",
    "minecraft:purpur_block": "minecraft:purpur_block",
    "minecraft:purpur_pillar": "minecraft:purpur_block",
    "minecraft:end_stone": "minecraft:end_stone",
    "minecraft:end_stone_bricks": "minecraft:end_bricks",
    "minecraft:end_rod": "minecraft:end_rod",
    "minecraft:shulker_box": "minecraft:undyed_shulker_box",
    "minecraft:barrel": "minecraft:barrel",
    "minecraft:campfire": "minecraft:campfire",
    "minecraft:lantern": "minecraft:lantern",
    "minecraft:soul_lantern": "minecraft:soul_lantern",
    "minecraft:beehive": "minecraft:beehive",
    "minecraft:bee_nest": "minecraft:bee_nest",
    "minecraft:honey_block": "minecraft:honey_block",
    "minecraft:honeycomb_block": "minecraft:honeycomb_block",
    "minecraft:target": "minecraft:target",
    "minecraft:ancient_debris": "minecraft:ancient_debris",
    "minecraft:nether_gold_ore": "minecraft:nether_gold_ore",
    "minecraft:crimson_nylium": "minecraft:crimson_nylium",
    "minecraft:warped_nylium": "minecraft:warped_nylium",
    "minecraft:crimson_stem": "minecraft:crimson_stem",
    "minecraft:warped_stem": "minecraft:warped_stem",
    "minecraft:shroomlight": "minecraft:shroomlight",
    "minecraft:blackstone": "minecraft:blackstone",
    "minecraft:gilded_blackstone": "minecraft:gilded_blackstone",
    "minecraft:crying_obsidian": "minecraft:crying_obsidian",
    "minecraft:respawn_anchor": "minecraft:respawn_anchor",
    "minecraft:calcite": "minecraft:calcite",
    "minecraft:tuff": "minecraft:tuff",
    "minecraft:amethyst_block": "minecraft:amethyst_block",
    "minecraft:budding_amethyst": "minecraft:budding_amethyst",
    "minecraft:deepslate": "minecraft:deepslate",
    "minecraft:cobbled_deepslate": "minecraft:cobbled_deepslate",
    "minecraft:deepslate_bricks": "minecraft:deepslate_bricks",
    "minecraft:deepslate_tiles": "minecraft:deepslate_tiles",
    "minecraft:reinforced_deepslate": "minecraft:reinforced_deepslate",
    "minecraft:mud": "minecraft:mud",
    "minecraft:packed_mud": "minecraft:packed_mud",
    "minecraft:mud_bricks": "minecraft:mud_bricks",
    "minecraft:mangrove_log": "minecraft:mangrove_log",
    "minecraft:mangrove_planks": "minecraft:mangrove_planks",
    "minecraft:cherry_log": "minecraft:cherry_log",
    "minecraft:cherry_planks": "minecraft:cherry_planks",
    "minecraft:bamboo_block": "minecraft:bamboo_block",
}
import struct as _struct
import gzip as _gzip
import io as _io
NBT_END       = 0
NBT_BYTE      = 1
NBT_SHORT     = 2
NBT_INT       = 3
NBT_LONG      = 4
NBT_FLOAT     = 5
NBT_DOUBLE    = 6
NBT_BYTE_ARRAY= 7
NBT_STRING    = 8
NBT_LIST      = 9
NBT_COMPOUND  = 10
NBT_INT_ARRAY = 11
NBT_LONG_ARRAY= 12
def _nbt_read_tag(buf: _io.BytesIO, tag_type: int):
    if tag_type == NBT_BYTE:
        return _struct.unpack(">b", buf.read(1))[0]
    elif tag_type == NBT_SHORT:
        return _struct.unpack(">h", buf.read(2))[0]
    elif tag_type == NBT_INT:
        return _struct.unpack(">i", buf.read(4))[0]
    elif tag_type == NBT_LONG:
        return _struct.unpack(">q", buf.read(8))[0]
    elif tag_type == NBT_FLOAT:
        return _struct.unpack(">f", buf.read(4))[0]
    elif tag_type == NBT_DOUBLE:
        return _struct.unpack(">d", buf.read(8))[0]
    elif tag_type == NBT_BYTE_ARRAY:
        length = _struct.unpack(">i", buf.read(4))[0]
        return list(_struct.unpack(f">{length}b", buf.read(length)))
    elif tag_type == NBT_STRING:
        length = _struct.unpack(">H", buf.read(2))[0]
        return buf.read(length).decode("utf-8", errors="replace")
    elif tag_type == NBT_LIST:
        elem_type = _struct.unpack(">b", buf.read(1))[0]
        length = _struct.unpack(">i", buf.read(4))[0]
        return [_nbt_read_tag(buf, elem_type) for _ in range(length)]
    elif tag_type == NBT_COMPOUND:
        d = {}
        while True:
            t = _struct.unpack(">b", buf.read(1))[0]
            if t == NBT_END:
                break
            name_len = _struct.unpack(">H", buf.read(2))[0]
            name = buf.read(name_len).decode("utf-8", errors="replace")
            d[name] = _nbt_read_tag(buf, t)
        return d
    elif tag_type == NBT_INT_ARRAY:
        length = _struct.unpack(">i", buf.read(4))[0]
        return list(_struct.unpack(f">{length}i", buf.read(length * 4)))
    elif tag_type == NBT_LONG_ARRAY:
        length = _struct.unpack(">i", buf.read(4))[0]
        return list(_struct.unpack(f">{length}q", buf.read(length * 8)))
    else:
        raise ValueError(f"Unknown NBT tag type: {tag_type}")
def read_java_nbt(data: bytes) -> dict:
    try:
        data = _gzip.decompress(data)
    except Exception:
        pass
    buf = _io.BytesIO(data)
    root_type = _struct.unpack(">b", buf.read(1))[0]
    name_len  = _struct.unpack(">H", buf.read(2))[0]
    buf.read(name_len)
    return _nbt_read_tag(buf, root_type)
def _nbt_write_tag(buf: _io.BytesIO, tag_type: int, value):
    if tag_type == NBT_BYTE:
        buf.write(_struct.pack("<b", int(value)))
    elif tag_type == NBT_SHORT:
        buf.write(_struct.pack("<h", int(value)))
    elif tag_type == NBT_INT:
        buf.write(_struct.pack("<i", int(value)))
    elif tag_type == NBT_LONG:
        buf.write(_struct.pack("<q", int(value)))
    elif tag_type == NBT_FLOAT:
        buf.write(_struct.pack("<f", float(value)))
    elif tag_type == NBT_DOUBLE:
        buf.write(_struct.pack("<d", float(value)))
    elif tag_type == NBT_BYTE_ARRAY:
        buf.write(_struct.pack("<i", len(value)))
        buf.write(_struct.pack(f"<{len(value)}b", *value))
    elif tag_type == NBT_STRING:
        encoded = str(value).encode("utf-8")
        buf.write(_struct.pack("<H", len(encoded)))
        buf.write(encoded)
    elif tag_type == NBT_LIST:
        if not value:
            buf.write(_struct.pack("<b", NBT_END))
            buf.write(_struct.pack("<i", 0))
        else:
            first = value[0]
            if isinstance(first, bool):   elem_type = NBT_BYTE
            elif isinstance(first, int):  elem_type = NBT_INT
            elif isinstance(first, float):elem_type = NBT_FLOAT
            elif isinstance(first, str):  elem_type = NBT_STRING
            elif isinstance(first, dict): elem_type = NBT_COMPOUND
            elif isinstance(first, list): elem_type = NBT_LIST
            else:                         elem_type = NBT_STRING
            buf.write(_struct.pack("<b", elem_type))
            buf.write(_struct.pack("<i", len(value)))
            for item in value:
                _nbt_write_tag(buf, elem_type, item)
    elif tag_type == NBT_COMPOUND:
        for k, v in value.items():
            t = _infer_nbt_type(v)
            buf.write(_struct.pack("<b", t))
            enc_k = k.encode("utf-8")
            buf.write(_struct.pack("<H", len(enc_k)))
            buf.write(enc_k)
            _nbt_write_tag(buf, t, v)
        buf.write(_struct.pack("<b", NBT_END))
    elif tag_type == NBT_INT_ARRAY:
        buf.write(_struct.pack("<i", len(value)))
        buf.write(_struct.pack(f"<{len(value)}i", *value))
    elif tag_type == NBT_LONG_ARRAY:
        buf.write(_struct.pack("<i", len(value)))
        buf.write(_struct.pack(f"<{len(value)}q", *value))
def _infer_nbt_type(value) -> int:
    if isinstance(value, bool):  return NBT_BYTE
    if isinstance(value, int):   return NBT_INT
    if isinstance(value, float): return NBT_FLOAT
    if isinstance(value, str):   return NBT_STRING
    if isinstance(value, dict):  return NBT_COMPOUND
    if isinstance(value, list):
        if not value:            return NBT_LIST
        first = value[0]
        if isinstance(first, bool):  return NBT_LIST
        if isinstance(first, int):   return NBT_INT_ARRAY
        if isinstance(first, float): return NBT_LIST
        if isinstance(first, dict):  return NBT_LIST
        if isinstance(first, list):  return NBT_LIST
        return NBT_LIST
    return NBT_STRING
def write_bedrock_nbt(root_name: str, compound: dict) -> bytes:
    buf = _io.BytesIO()
    buf.write(_struct.pack("<b", NBT_COMPOUND))
    enc = root_name.encode("utf-8")
    buf.write(_struct.pack("<H", len(enc)))
    buf.write(enc)
    _nbt_write_tag(buf, NBT_COMPOUND, compound)
    return buf.getvalue()
def _remap_block_name(java_name: str, namespace: str) -> str:
    if not java_name:
        return "minecraft:air"
    if ":" in java_name:
        ns, name = java_name.split(":", 1)
        if ns == "minecraft":
            return JAVA_TO_BEDROCK_BLOCK.get(java_name, "minecraft:air")
        else:
            return f"{namespace}:{sanitize_identifier(name)}"
    return JAVA_TO_BEDROCK_BLOCK.get(f"minecraft:{java_name}", f"minecraft:{java_name}")
def _convert_block_state(java_state: dict, bedrock_name: str) -> dict:
    if not java_state:
        return {}
    bedrock_states = {}
    PROP_MAP = {
        "facing":        "minecraft:facing_direction",
        "half":          None,
        "waterlogged":   None,
        "powered":       "powered_bit",
        "open":          "open_bit",
        "lit":           "lit",
        "persistent":    "persistent_bit",
        "snowy":         None,
        "axis":          "pillar_axis",
        "type":          None,
        "shape":         None,
        "age":           "age",
        "level":         "liquid_depth",
        "layers":        "height",
        "distance":      None,
        "occupied":      None,
        "part":          None,
        "in_wall":       None,
        "attached":      None,
        "disarmed":      None,
        "hinge":         None,
        "delay":         "output_lit_bit",
        "locked":        None,
    }
    for k, v in java_state.items():
        bedrock_key = PROP_MAP.get(k, k)
        if bedrock_key is None:
            continue
        if v == "true":  v = 1
        elif v == "false": v = 0
        elif k == "facing":
            v = {"north": 2, "south": 3, "west": 4, "east": 5,
                 "up": 1, "down": 0}.get(v, 0)
            bedrock_key = "facing_direction"
        elif k == "axis":
            v = {"x": 1, "y": 0, "z": 2}.get(v, 0)
            bedrock_key = "pillar_axis"
        try:
            v = int(v)
        except (ValueError, TypeError):
            pass
        bedrock_states[bedrock_key] = v
    return bedrock_states
def convert_java_nbt_to_mcstructure(nbt_data: dict, namespace: str) -> dict:
    size = nbt_data.get("size", [1, 1, 1])
    sx, sy, sz = int(size[0]), int(size[1]), int(size[2])
    total = sx * sy * sz
    BEDROCK_BLOCK_VERSION = 17959425
    java_palette = nbt_data.get("palette", [])
    bedrock_palette = []
    dedup_map  = {}
    java_to_bp = {}
    air_key = ("minecraft:air", ())
    dedup_map[air_key] = 0
    bedrock_palette.append({"name": "minecraft:air", "states": {}, "version": BEDROCK_BLOCK_VERSION})
    for i, entry in enumerate(java_palette):
        java_name = entry.get("Name", "minecraft:air")
        java_props = entry.get("Properties", {})
        bedrock_name = _remap_block_name(java_name, namespace)
        bedrock_states = _convert_block_state(java_props, bedrock_name)
        key = (bedrock_name, tuple(sorted(bedrock_states.items())))
        if key not in dedup_map:
            dedup_map[key] = len(bedrock_palette)
            bedrock_palette.append({
                "name": bedrock_name,
                "states": bedrock_states,
                "version": BEDROCK_BLOCK_VERSION
            })
        java_to_bp[i] = dedup_map[key]
    water_key = ("minecraft:water", ())
    if water_key not in dedup_map:
        dedup_map[water_key] = len(bedrock_palette)
        bedrock_palette.append({"name": "minecraft:water", "states": {"liquid_depth": 0}, "version": BEDROCK_BLOCK_VERSION})
    water_idx = dedup_map[water_key]
    layer0 = [-1] * total
    layer1 = [-1] * total
    block_position_data = {}
    for block in nbt_data.get("blocks", []):
        pos = block.get("pos", [0, 0, 0])
        state_idx = int(block.get("state", 0))
        x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
        if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
            continue
        flat_idx = x + z * sx + y * sx * sz
        bedrock_idx = java_to_bp.get(state_idx, 0)
        layer0[flat_idx] = bedrock_idx
        java_entry = java_palette[state_idx] if state_idx < len(java_palette) else {}
        if java_entry.get("Properties", {}).get("waterlogged") == "true":
            layer1[flat_idx] = water_idx
        block_nbt = block.get("nbt")
        if block_nbt and isinstance(block_nbt, dict):
            converted_be = _convert_block_entity_nbt(block_nbt, namespace)
            if converted_be:
                block_position_data[str(flat_idx)] = {"block_entity_data": converted_be}
    bedrock_entities = []
    for i, ent in enumerate(nbt_data.get("entities", [])):
        try:
            pos = ent.get("pos", [0.0, 0.0, 0.0])
            ent_nbt = ent.get("nbt", {})
            entity_id = ent_nbt.get("id", "")
            if not entity_id:
                continue
            if ":" not in entity_id:
                entity_id = f"minecraft:{entity_id.lower()}"
            else:
                ns_e, name_e = entity_id.split(":", 1)
                if ns_e != "minecraft":
                    entity_id = f"{namespace}:{sanitize_identifier(name_e)}"
            bedrock_entities.append({
                "identifier": entity_id,
                "Pos": [float(p) for p in pos],
                "UniqueID": -(i + 1),
                "Tags": [],
            })
        except Exception:
            pass
    return {
        "format_version": 1,
        "size": [sx, sy, sz],
        "structure_world_origin": [0, 0, 0],
        "structure": {
            "block_indices": [layer0, layer1],
            "entities": bedrock_entities,
            "palette": {
                "default": {
                    "block_palette": bedrock_palette,
                    "block_position_data": block_position_data
                }
            }
        }
    }
def _convert_block_entity_nbt(java_nbt: dict, namespace: str) -> Optional[dict]:
    be_id = java_nbt.get("id", "")
    if not be_id:
        return None
    if ":" in be_id:
        be_id = be_id.split(":", 1)[1]
    be_id = be_id.lower()
    result = {"id": be_id, "isMovable": 1}
    if be_id in ("chest", "trapped_chest", "barrel", "shulker_box", "hopper", "dropper", "dispenser"):
        items = java_nbt.get("Items", [])
        bedrock_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id", "minecraft:air")
            if ":" in item_id:
                ns_i, name_i = item_id.split(":", 1)
                if ns_i != "minecraft":
                    item_id = f"{namespace}:{sanitize_identifier(name_i)}"
            bedrock_items.append({
                "Count": item.get("Count", 1),
                "Damage": 0,
                "Name": item_id,
                "Slot": item.get("Slot", 0),
                "WasPickedUp": 0,
            })
        if bedrock_items:
            result["Items"] = bedrock_items
    elif be_id == "mob_spawner":
        spawn_data = java_nbt.get("SpawnData", {})
        entity_id = spawn_data.get("entity", {}).get("id", "") or java_nbt.get("EntityId", "")
        if not entity_id:
            entity_id = "minecraft:pig"
        if ":" not in entity_id:
            entity_id = f"minecraft:{entity_id.lower()}"
        result["EntityIdentifier"] = entity_id
        result["Delay"] = java_nbt.get("Delay", 20)
        result["MaxNearbyEntities"] = java_nbt.get("MaxNearbyEntities", 6)
        result["MaxSpawnDelay"] = java_nbt.get("MaxSpawnDelay", 800)
        result["MinSpawnDelay"] = java_nbt.get("MinSpawnDelay", 200)
        result["RequiredPlayerRange"] = java_nbt.get("RequiredPlayerRange", 16)
        result["SpawnCount"] = java_nbt.get("SpawnCount", 4)
        result["SpawnRange"] = java_nbt.get("SpawnRange", 4)
    elif be_id in ("sign", "hanging_sign"):
        import json as _json
        for side in ("front_text", "back_text", "Text1", "Text2", "Text3", "Text4"):
            val = java_nbt.get(side, "")
            if isinstance(val, dict):
                messages = val.get("messages", [])
                lines = []
                for msg in messages:
                    try:
                        parsed = _json.loads(msg)
                        text = parsed.get("text", "") if isinstance(parsed, dict) else str(parsed)
                    except Exception:
                        text = str(msg).strip('"')
                    lines.append(text)
                result["Text"] = "\n".join(lines)
                break
            elif isinstance(val, str) and val:
                try:
                    parsed = _json.loads(val)
                    result[side] = parsed.get("text", val) if isinstance(parsed, dict) else val
                except Exception:
                    result[side] = val
    elif be_id in ("furnace", "smoker", "blast_furnace"):
        result["BurnTime"] = java_nbt.get("BurnTime", 0)
        result["CookTime"] = java_nbt.get("CookTime", 0)
        result["CookTimeTotal"] = java_nbt.get("CookTimeTotal", 200)
    return result if len(result) > 2 else None
def extract_structure_metadata_from_java(java_code: str, namespace: str) -> dict:
    meta = {
        "biomes": ["overworld"],
        "step": "surface_pass",
        "spacing": 32,
        "separation": 8,
        "salt": 0,
        "start_height": 64,
        "terrain_adaptation": "beard_thin",
    }
    biome_matches = re.findall(
        r'(?:BiomeTags|Tags\.Biomes|BiomeDictionary)[^.(]*\.([A-Z_]+)', java_code)
    for b in biome_matches:
        bl = b.lower().replace("is_", "").replace("has_", "")
        for k, v in JAVA_BIOME_TO_BEDROCK.items():
            if k in bl:
                if v not in meta["biomes"]:
                    meta["biomes"].append(v)
    m = re.search(r'spacing\s*[=,]\s*(\d+)', java_code)
    if m: meta["spacing"] = int(m.group(1))
    m = re.search(r'separation\s*[=,]\s*(\d+)', java_code)
    if m: meta["separation"] = int(m.group(1))
    m = re.search(r'salt\s*[=,]\s*(\d+)', java_code)
    if m: meta["salt"] = int(m.group(1))
    if re.search(r'NETHER|nether', java_code, re.I): meta["biomes"] = ["nether"]; meta["step"] = "surface_pass"
    if re.search(r'THE_END|the_end', java_code, re.I): meta["biomes"] = ["the_end"]
    if re.search(r'GenerationStep\.Decoration\.UNDERGROUND', java_code): meta["step"] = "underground_pass"
    if re.search(r'GenerationStep\.Decoration\.VEGETAL', java_code): meta["step"] = "surface_pass"
    m = re.search(r'startHeight[^;]*?(-?\d+)', java_code)
    if m: meta["start_height"] = int(m.group(1))
    return meta
def generate_feature_json(structure_name: str, namespace: str) -> dict:
    full_id = f"{namespace}:{structure_name}"
    return {
        "format_version": "1.13.0",
        "minecraft:structure_template_feature": {
            "description": {
                "identifier": f"{namespace}:{structure_name}_feature"
            },
            "structure_name": full_id,
            "adjustment_radius": 4,
            "facing_direction": "random",
            "constraints": {
                "unburied": {},
                "block_intersection": {
                    "block_allowlist": [
                        "minecraft:air",
                        "minecraft:grass",
                        "minecraft:dirt",
                        "minecraft:stone"
                    ]
                }
            }
        }
    }
def generate_feature_rule_json(structure_name: str, namespace: str, meta: dict) -> dict:
    biome_filters = []
    for biome in meta.get("biomes", ["overworld"]):
        biome_filters.append({
            "test": "has_biome_tag",
            "operator": "==",
            "value": biome
        })
    spacing = meta.get("spacing", 32)
    chance = max(0.01, min(1.0, round(1.0 / max(1, spacing / 8), 3)))
    return {
        "format_version": "1.13.0",
        "minecraft:feature_rules": {
            "description": {
                "identifier": f"{namespace}:{structure_name}_feature_rule",
                "places_feature": f"{namespace}:{structure_name}_feature"
            },
            "conditions": {
                "placement_pass": meta.get("step", "surface_pass"),
                "minecraft:biome_filter": biome_filters if len(biome_filters) > 1 else biome_filters[0] if biome_filters else {"test": "has_biome_tag", "value": "overworld"}
            },
            "distribution": {
                "iterations": 1,
                "scatter_chance": str(chance),
                "x": {"distribution": "uniform", "extent": [0, 16]},
                "y": meta.get("start_height", 64),
                "z": {"distribution": "uniform", "extent": [0, 16]}
            }
        }
    }
def process_structures_from_jar(jar_path: str, namespace: str, java_files: dict = None):
    if not jar_path or not os.path.exists(jar_path):
        return
    java_files = java_files or {}
    structures_processed = 0
    features_written = 0
    mcstructure_dir = os.path.join(BP_FOLDER, "structures")
    features_dir    = os.path.join(BP_FOLDER, "features")
    feat_rules_dir  = os.path.join(BP_FOLDER, "feature_rules")
    os.makedirs(mcstructure_dir, exist_ok=True)
    os.makedirs(features_dir, exist_ok=True)
    os.makedirs(feat_rules_dir, exist_ok=True)
    structure_meta_map = {}
    for path, code in java_files.items():
        if re.search(r'extends\s+(?:Structure|StructureFeature|JigsawStructure)', code):
            cls = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
            structure_meta_map[cls] = extract_structure_metadata_from_java(code, namespace)
    worldgen_metas = {}
    try:
        with zipfile.ZipFile(jar_path, "r") as jar:
            for file in jar.namelist():
                lower = file.lower()
                if lower.endswith(".nbt") and "/structures/" in lower:
                    try:
                        with jar.open(file) as f:
                            nbt_raw = f.read()
                        nbt_data = read_java_nbt(nbt_raw)
                        after = lower.split("/structures/", 1)[1]
                        stem = os.path.splitext(after)[0].replace("/", "_").replace("\\", "_")
                        safe_stem = sanitize_identifier(stem)
                        mcstructure = convert_java_nbt_to_mcstructure(nbt_data, namespace)
                        mcstructure_nbt = write_bedrock_nbt("", mcstructure)
                        out_path = os.path.join(mcstructure_dir, f"{safe_stem}.mcstructure")
                        with open(out_path, "wb") as out_f:
                            out_f.write(mcstructure_nbt)
                        print(f"[structure] Converted {os.path.basename(file)} -> {safe_stem}.mcstructure "
                              f"({mcstructure['size']})")
                        meta = {"biomes": ["overworld"], "step": "surface_pass",
                                "spacing": 32, "separation": 8, "start_height": 64}
                        for cls_name, cls_meta in structure_meta_map.items():
                            if sanitize_identifier(cls_name.lower().replace("structure","")) in safe_stem:
                                meta = cls_meta
                                break
                        feat_json = generate_feature_json(safe_stem, namespace)
                        safe_write_json(os.path.join(features_dir, f"{safe_stem}_feature.json"), feat_json)
                        rule_json = generate_feature_rule_json(safe_stem, namespace, meta)
                        safe_write_json(os.path.join(feat_rules_dir, f"{safe_stem}_feature_rule.json"), rule_json)
                        structures_processed += 1
                        features_written += 1
                    except Exception as e:
                        print(f"[structure]  Failed to convert {file}: {e}")
                elif "/worldgen/structure/" in lower and lower.endswith(".json"):
                    try:
                        with jar.open(file) as f:
                            wg_data = json.load(f)
                        stem = os.path.splitext(os.path.basename(file))[0]
                        safe_stem = sanitize_identifier(stem)
                        biome_tag = wg_data.get("biomes", "")
                        if isinstance(biome_tag, str) and ":" in biome_tag:
                            biome_tag = biome_tag.split(":")[1]
                        worldgen_metas[safe_stem] = {
                            "raw": wg_data,
                            "biome_hint": biome_tag
                        }
                    except Exception:
                        pass
                elif "/worldgen/template_pool/" in lower and lower.endswith(".json"):
                    try:
                        with jar.open(file) as f:
                            pool_data = json.load(f)
                        safe_stem = sanitize_identifier(os.path.splitext(os.path.basename(file))[0])
                        ref_path = os.path.join(BP_FOLDER, "structures", f"_pool_{safe_stem}.json")
                        with open(ref_path, "w", encoding="utf-8") as out_f:
                            json.dump({
                                "__note": "Jigsaw template pool - manual conversion required",
                                "__source": file,
                                "data": pool_data
                            }, out_f, indent=2)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[structure]  JAR read error: {e}")
    print(f"[structure] Processed {structures_processed} structure(s), "
          f"wrote {features_written} feature+rule pair(s)")
def extract_logo_from_jar(jar_path: str) -> Optional[str]:
    if not jar_path or not os.path.exists(jar_path):
        return None
    icon_candidates = [
        "pack.png", "icon.png", "logo.png", "pack_icon.png",
        "META-INF/pack.png", "META-INF/icon.png", "META-INF/logo.png"
    ]
    try:
        with zipfile.ZipFile(jar_path, "r") as jar:
            for candidate in icon_candidates:
                try:
                    with jar.open(candidate) as f:
                        icon_data = f.read()
                    temp_dir = ".temp_logo_extract"
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_path = os.path.join(temp_dir, "pack_icon.png")
                    with open(temp_path, "wb") as out:
                        out.write(icon_data)
                    print(f"[icon] Extracted {candidate} from JAR")
                    return temp_path
                except KeyError:
                    continue
    except Exception as e:
        print(f"[icon] Failed to extract icon from JAR: {e}")
    return None





_MIXIN_KINDS = (
    'mixin', 'inject', 'redirect', 'overwrite', 'accessor', 'invoker',
    'shadow', 'unique', 'mutable', 'final', 'modifyvariable', 'modifyarg',
    'modifyargs', 'modifyconstant', 'wrapoperation', 'wrapwithcondition',
    'slice', 'at', 'group', 'coerce', 'desc'
)

_MIXIN_TARGET_ALIASES = {
    'PlayerEntity': 'Player',
    'ServerPlayerEntity': 'ServerPlayer',
    'ClientPlayerEntity': 'Player',
    'LivingEntity': 'LivingEntity',
    'PathfinderMob': 'PathfinderMob',
    'AbstractClientPlayerEntity': 'Player',
    'AbstractArrowEntity': 'AbstractArrow',
    'ThrownItemEntity': 'ItemEntity',
    'ItemEntity': 'ItemEntity',
    'BlockEntity': 'BlockEntity',
    'TileEntity': 'BlockEntity',
    'World': 'Level',
    'ServerWorld': 'ServerLevel',
    'ClientWorld': 'Level',
    'Level': 'Level',
    'ServerLevel': 'ServerLevel',
    'MinecraftServer': 'ServerLevel',
    'Block': 'Block',
    'AbstractBlock': 'AbstractBlock',
    'Item': 'Item',
    'ItemStack': 'ItemStack',
    'Screen': 'Screen',
    'HandledScreen': 'Screen',
    'AbstractContainerScreen': 'Screen',
    'ContainerScreen': 'Screen',
    'GuiScreen': 'Screen',
}

_MIXIN_METHOD_HINTS = {
    'tick': 'system.runInterval',
    'serverTick': 'system.runInterval',
    'clientTick': 'system.runInterval',
    'onTick': 'system.runInterval',
    'update': 'system.runInterval',
    'use': 'world.afterEvents.itemUse',
    'onUse': 'world.afterEvents.itemUse',
    'appendTooltip': 'world.afterEvents.itemUse',
    'interact': 'world.afterEvents.playerInteractWithEntity',
    'interactAt': 'world.afterEvents.playerInteractWithEntity',
    'attack': 'world.afterEvents.entityHitEntity',
    'performAttack': 'world.afterEvents.entityHitEntity',
    'hurt': 'world.afterEvents.entityHurt',
    'damage': 'world.afterEvents.entityHurt',
    'die': 'world.afterEvents.entityDie',
    'place': 'world.afterEvents.playerPlaceBlock',
    'onBlockActivated': 'world.afterEvents.playerInteractWithBlock',
    'onRemove': 'world.afterEvents.playerBreakBlock',
    'playerDestroy': 'world.afterEvents.playerBreakBlock',
    'onEntityHit': 'world.afterEvents.entityHitEntity',
    'shoot': 'world.afterEvents.projectileHitEntity',
    'explode': 'world.afterEvents.explosion',
    'finishUsingItem': 'world.afterEvents.useItem',
    'onCraftedBy': 'world.afterEvents.crafted',
}

_MIXIN_TARGET_EVENT_HINTS = {
    'Player': 'world.afterEvents.playerInteractWithEntity',
    'ServerPlayer': 'world.afterEvents.playerInteractWithEntity',
    'LivingEntity': 'world.afterEvents.entityHurt',
    'Mob': 'world.afterEvents.entitySpawn',
    'PathfinderMob': 'world.afterEvents.entitySpawn',
    'Animal': 'world.afterEvents.entitySpawn',
    'Monster': 'world.afterEvents.entitySpawn',
    'Entity': 'world.afterEvents.entitySpawn',
    'ItemEntity': 'world.afterEvents.itemStartPickUp',
    'AbstractArrow': 'world.afterEvents.projectileHitEntity',
    'Arrow': 'world.afterEvents.projectileHitEntity',
    'ThrownPotion': 'world.afterEvents.projectileHitEntity',
    'BlockEntity': 'world.afterEvents.playerInteractWithBlock',
    'Level': 'world.afterEvents.worldInitialize',
    'ServerLevel': 'world.afterEvents.worldInitialize',
    'Screen': 'system.runInterval',
    'Item': 'world.afterEvents.itemUse',
    'Block': 'world.afterEvents.playerPlaceBlock',
    'AbstractBlock': 'world.afterEvents.playerPlaceBlock',
}

_SUPPORTED_MIXIN_ANNOTATIONS = {
    'Mixin', 'Inject', 'Redirect', 'Overwrite', 'Accessor', 'Invoker',
    'Shadow', 'Unique', 'Mutable', 'Final', 'ModifyVariable', 'ModifyArg',
    'ModifyArgs', 'ModifyConstant', 'WrapOperation', 'WrapWithCondition',
    'Slice', 'At', 'Group', 'Coerce', 'Desc', 'Surrogate'
}


def _is_mixin_source(code: str, path: str = '') -> bool:
    code = code or ''
    low = (path or '').lower()
    if '@Mixin' in code or any(f'@{ann}' in code for ann in _SUPPORTED_MIXIN_ANNOTATIONS if ann != 'Mixin'):
        return True
    return 'mixin' in low


def _normalize_mixin_target(target: Optional[str]) -> Optional[str]:
    if not target:
        return None
    t = str(target).strip().strip('"\'')
    t = t.replace('/', '.').replace('$', '.')
    t = re.sub(r'<.*?>', '', t)
    t = t.split('.')[-1]
    return _MIXIN_TARGET_ALIASES.get(t, t)


def _extract_mixin_targets(code: str) -> list[str]:
    code = code or ''
    targets: list[str] = []
    for m in re.finditer(r'@Mixin\s*\((.*?)\)', code, re.DOTALL):
        body = m.group(1)
        for raw in re.findall(r'([A-Za-z_][\w.$/]+)\.class', body):
            targets.append(_normalize_mixin_target(raw))
        for raw in re.findall(r'"([^"]+)"', body):
            if '/' in raw or '.' in raw:
                targets.append(_normalize_mixin_target(raw))
    cleaned = [t for t in targets if t]
    return list(dict.fromkeys(cleaned))


def _annotation_arg_block(text: str, annotation: str) -> str:
    m = re.search(rf'@{re.escape(annotation)}\s*\((.*?)\)', text, re.DOTALL)
    return m.group(1) if m else ''


def _method_annotations(method_block: str) -> list[str]:
    return re.findall(r'@([A-Za-z_][A-Za-z0-9_]*)\b', method_block or '')


def _extract_annotated_methods(code: str) -> list[dict]:
    cleaned = _strip_java_comments(code or '')
    results: list[dict] = []
    pat = re.compile(
        r'(?P<ann>(?:\s*@\w+(?:\([^)]*\))?\s*)+)' \
        r'(?P<sig>(?:public|protected|private|static|final|native|synchronized|abstract|default|\s|@\w+(?:\([^)]*\))?\s*)+' \
        r'(?P<rettype>[\w<>,\[\].?\s]+?)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?:throws\s+[^{]+)?\{)',
        re.DOTALL,
    )
    for m in pat.finditer(cleaned):
        sig = m.group('sig')
        brace = cleaned.find('{', m.start('sig'))
        if brace == -1:
            continue
        body = _extract_block(cleaned, m.start('sig'))
        ann_text = m.group('ann')
        results.append({
            'name': m.group('name'),
            'return_type': (m.group('rettype') or '').strip(),
            'annotations': _method_annotations(ann_text),
            'annotation_text': ann_text,
            'signature_text': sig,
            'body': body,
            'params': m.group('params') or '',
        })
    return results


def _pick_mixin_event(target_cls: Optional[str], method_name: str, annotation_args: str = '', body: str = '') -> Optional[str]:
    hay = f'{target_cls or ""} {method_name} {annotation_args} {body}'.lower()
    if 'construct' in hay or '<init>' in hay:
        return 'world.afterEvents.entitySpawn'
    if method_name in _MIXIN_METHOD_HINTS:
        return _MIXIN_METHOD_HINTS[method_name]
    for key, event in _MIXIN_METHOD_HINTS.items():
        if key in hay:
            return event
    if any(k in hay for k in ('hurt', 'damage', 'attack')):
        return 'world.afterEvents.entityHurt'
    if any(k in hay for k in ('tick', 'update')):
        return 'system.runInterval'
    if any(k in hay for k in ('use', 'interact', 'rightclick', 'right_click')):
        return 'world.afterEvents.itemUse'
    if any(k in hay for k in ('place', 'break', 'destroy', 'remove')):
        return 'world.afterEvents.playerBreakBlock'
    if any(k in hay for k in ('spawn', 'join', 'load', 'init')):
        return 'world.afterEvents.entitySpawn'
    return None


def _accessor_member_name(method_name: str, annotation_args: str = '') -> str:
    if annotation_args:
        m = re.search(r'value\s*=\s*"([^"]+)"', annotation_args)
        if m:
            return m.group(1)
        m = re.search(r'target\s*=\s*"([^"]+)"', annotation_args)
        if m:
            return m.group(1)
    for prefix in ('get', 'set', 'is', 'call', 'invoke'):
        if method_name.startswith(prefix) and len(method_name) > len(prefix):
            stem = method_name[len(prefix):]
            return stem[:1].lower() + stem[1:]
    return method_name


def _emit_preserved_body(body: str) -> list[str]:
    lines: list[str] = []
    if not body:
        return lines
    for raw in body.splitlines():
        raw = raw.rstrip()
        if raw.strip():
            lines.append(f'// {raw.strip()}')
    return lines


def _emit_js_hook(event_name: str, body_lines: list[str], method_name: str, annotation_args: str = '', cancellable: bool = False) -> list[str]:
    out: list[str] = []
    if event_name == 'system.runInterval':
        out.append(f'// {method_name}: scheduled interval hook')
        out.append('system.runInterval(() => {')
        out.extend(body_lines or ['    // no automatic translation available'])
        out.append('}, 1);')
        return out
    out.append(f'// {method_name}: {event_name}')
    out.append(f'{event_name}.subscribe((event) => {{')
    if cancellable:
        out.append('    let cancelled = false;')
        out.append('    const cancel = () => { cancelled = true; };')
    if body_lines:
        for line in body_lines:
            if line.startswith('//'):
                out.append(f'    {line}')
            else:
                out.append(line)
    else:
        out.append('    const entity = event.entity ?? event.player ?? event.hurtEntity ?? event.block ?? event.itemEntity ?? null;')
        out.append('    if (!entity) return;')
    if cancellable:
        out.append('    if (cancelled) return;')
    out.append('});')
    return out


def _emit_accessor_stub(cls_name: str, method_name: str, annotation_args: str) -> list[str]:
    member = _accessor_member_name(method_name, annotation_args)
    is_setter = method_name.startswith('set')
    lines = [f'// @Accessor {method_name}']
    if is_setter:
        lines += [
            f'export function {sanitize_identifier(cls_name)}_{sanitize_identifier(method_name)}(target, value) {{',
            f'    if (!target) return;',
            f'    target[{json.dumps(member)}] = value;',
            '}',
        ]
    else:
        lines += [
            f'export function {sanitize_identifier(cls_name)}_{sanitize_identifier(method_name)}(target) {{',
            f'    if (!target) return undefined;',
            f'    return target[{json.dumps(member)}];',
            '}',
        ]
    return lines


def _emit_invoker_stub(cls_name: str, method_name: str) -> list[str]:
    sid = sanitize_identifier(cls_name)
    mid = sanitize_identifier(method_name)
    return [
        f'// @Invoker {method_name}',
        f'export function {sid}_{mid}(target, ...args) {{',
        '    if (!target) return undefined;',
        f'    const fn = target[{json.dumps(method_name)}];',
        '    if (typeof fn !== "function") return undefined;',
        '    return fn.apply(target, args);',
        '}',
    ]


def _emit_shadow_notice(method_name: str) -> list[str]:
    return [f'// @Shadow {method_name} is preserved as a field/method alias in source only.']


def _mixin_manifest_entry(path: str, cls_name: str, targets: list[str], methods: list[dict]) -> dict:
    return {
        'path': path,
        'class_name': cls_name,
        'targets': targets,
        'methods': [
            {
                'name': m['name'],
                'annotations': m['annotations'],
                'return_type': m['return_type'],
                'params': m['params'],
            } for m in methods
        ],
    }


def scan_mixins(java_files: Dict[str, str], namespace: str) -> list[str]:
    notes: list[str] = []
    out_dir = os.path.join(BP_FOLDER, 'scripts')
    os.makedirs(out_dir, exist_ok=True)
    manifest: list[dict] = []

    for path, code in java_files.items():
        if not _is_mixin_source(code, path):
            continue

        cls_name = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
        safe_name = sanitize_identifier(cls_name)
        targets = _extract_mixin_targets(code)
        methods = _extract_annotated_methods(code)
        if not methods and '@Mixin' not in code:
            continue

        script_lines = [
            'import { world, system } from "@minecraft/server";',
            '',
            f'// Auto-generated mixin bridge for {cls_name}',
        ]
        if targets:
            script_lines.append(f'// Targets: {", ".join(targets)}')
        script_lines.append('')

        wrote_anything = bool(targets or methods)
        if not methods:
            script_lines += [
                f'// No method annotations were recognized for {cls_name}.',
                f'// The source still qualifies as a mixin and is preserved here for manual porting.',
            ]
        for target in targets or [None]:
            event_hint = _MIXIN_TARGET_EVENT_HINTS.get(target or '')
            if event_hint:
                script_lines.append(f'// Target hint: {target} -> {event_hint}')

        for method in methods:
            anns = set(method['annotations'])
            ann_text = method['annotation_text']
            body = method['body'] or ''
            method_name = method['name']
            cancellable = 'Inject' in anns and 'cancellable = true' in ann_text.replace(' ', '').lower()
            primary_target = targets[0] if targets else None
            event_name = _pick_mixin_event(primary_target, method_name, ann_text, body)
            body_lines = _translate_mixin_body_to_js(body, namespace, safe_name) if body else []
            if body_lines:
                body_lines = [f'    {ln}' if not ln.startswith('//') else f'    {ln}' for ln in body_lines]

            if 'Accessor' in anns:
                script_lines.extend(_emit_accessor_stub(cls_name, method_name, ann_text))
                script_lines.append('')
                continue
            if 'Invoker' in anns:
                script_lines.extend(_emit_invoker_stub(cls_name, method_name))
                script_lines.append('')
                continue
            if 'Shadow' in anns:
                script_lines.extend(_emit_shadow_notice(method_name))
                script_lines.append('')
                continue
            if 'Unique' in anns:
                script_lines.append(f'// @Unique {method_name} is local helper logic and stays embedded below.')
                script_lines.extend(_emit_preserved_body(body))
                script_lines.append('')
                continue
            if 'Overwrite' in anns:
                if event_name:
                    script_lines.extend(_emit_js_hook(event_name, body_lines or _emit_preserved_body(body), method_name, ann_text, cancellable))
                    script_lines.append('')
                else:
                    notes.append(f'[mixin] {cls_name}: @Overwrite {method_name} could not be mapped automatically; preserved as comments.')
                    script_lines.append(f'// @Overwrite {method_name}')
                    script_lines.extend(_emit_preserved_body(body))
                    script_lines.append('')
                continue
            if 'Inject' in anns:
                if event_name:
                    script_lines.append(f'// @Inject {method_name}{" (cancellable)" if cancellable else ""}')
                    script_lines.extend(_emit_js_hook(event_name, body_lines or _emit_preserved_body(body), method_name, ann_text, cancellable))
                    script_lines.append('')
                else:
                    notes.append(f'[mixin] {cls_name}: @Inject {method_name} has no confident Bedrock hook; kept as a preserved block.')
                    script_lines.append(f'// @Inject {method_name}')
                    script_lines.extend(_emit_preserved_body(body))
                    script_lines.append('')
                continue
            if 'Redirect' in anns:
                notes.append(f'[mixin] {cls_name}: @Redirect {method_name} is call-site rewriting; emitted as a manual bridge note.')
                script_lines.append(f'// @Redirect {method_name} cannot be fully translated in Bedrock.')
                script_lines.extend(_emit_preserved_body(body))
                script_lines.append('')
                continue
            if 'ModifyVariable' in anns or 'ModifyArg' in anns or 'ModifyArgs' in anns or 'ModifyConstant' in anns or 'WrapOperation' in anns or 'WrapWithCondition' in anns:
                notes.append(f'[mixin] {cls_name}: {method_name} uses bytecode-level mutation ({", ".join(sorted(anns))}); emitted as a manual helper stub.')
                script_lines.append(f'// @{", @".join(sorted(anns))} {method_name}')
                script_lines.extend(_emit_preserved_body(body))
                script_lines.append('')
                continue


            script_lines.append(f'// {method_name} preserved from mixin source')
            script_lines.extend(_emit_preserved_body(body))
            script_lines.append('')

        if '@Mixin' in code and not targets:
            notes.append(f'[mixin] {cls_name}: @Mixin target could not be resolved; preserved source emitted.')
        if 'org.spongepowered.asm.mixin' in code.lower() or 'fabric' in code.lower() or 'quilt' in code.lower():
            notes.append(f'[mixin] {cls_name}: Fabric/Quilt mixin detected; generated bridge plus preservation stubs.')

        manifest.append(_mixin_manifest_entry(path, cls_name, targets, methods))
        out_path = os.path.join(out_dir, f'mixin_{safe_name}.js')
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(script_lines).rstrip() + '\n')
        print(f'[mixin] Wrote {out_path}')

    if manifest:
        _safe_json_dump(os.path.join(OUTPUT_DIR, 'mixin_manifest.json'), manifest)
    return notes


def scan_fabric_quilt_mixins(java_files: Dict[str, str], namespace: str) -> list[str]:
    return scan_mixins(java_files, namespace)


def _enhanced_postpass(namespace: str, java_files: Dict[str, str]) -> None:
    loader = _detect_project_loader()
    notes = [f'[loader] detected project loader: {loader}']
    mixin_notes = scan_mixins(java_files, namespace)
    notes.extend(mixin_notes)
    scripts_dir = os.path.join(BP_FOLDER, 'scripts')
    os.makedirs(scripts_dir, exist_ok=True)
    runtime_path = os.path.join(scripts_dir, 'runtime_bridge.js')
    with open(runtime_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(generate_bedrock_runtime_bridge(namespace)))
    main_path = os.path.join(scripts_dir, 'main.js')
    _ensure_main_import(main_path, 'import "./runtime_bridge.js";\n')
    if os.path.exists(main_path):
        _ensure_main_import(main_path, 'import "./cap_registry.js";\n')
    report = {
        'namespace': namespace,
        'loader': loader,
        'java_files': len(java_files),
        'mixins': sum(1 for p, c in java_files.items() if _is_mixin_source(c, p)),
        'notes': notes[:500],
    }
    _safe_json_dump(os.path.join(OUTPUT_DIR, 'conversion_report.json'), report)
    if notes:
        port_notes = os.path.join(BP_FOLDER, 'PORTING_NOTES.txt')
        os.makedirs(os.path.dirname(port_notes), exist_ok=True)
        with open(port_notes, 'a', encoding='utf-8') as fh:
            fh.write('\n'.join(notes) + '\n')

def run_pipeline():
    _orig = _logger._original_print
    jar_path = find_jar_file(".")
    if jar_path:
        jar_base_raw = os.path.splitext(os.path.basename(jar_path))[0]
        _orig(f"    Found JAR: {os.path.basename(jar_path)}")
    else:
        jar_base_raw = os.path.split(os.getcwd())[-1]
        _orig("     No .jar found — using folder name as namespace, skipping JAR assets")
    pack_display_name = jar_base_raw
    namespace = sanitize_identifier(jar_base_raw) or "converted"
    ensure_dirs()
    if jar_path:
        with _logger.phase("Extracting JAR assets", total=0, unit="step", colour="blue"):
            jar_loader = detect_loader_from_jar(jar_path)
            print(f"[loader] {jar_loader}")
            copy_assets_from_jar(jar_path, RP_FOLDER)
            copy_geckolib_animations_from_jar(jar_path, RP_FOLDER)
            logo = extract_logo_from_jar(jar_path)
            if logo:
                try:
                    dest_bp = os.path.join(BP_FOLDER, "pack_icon.png")
                    dest_rp = os.path.join(RP_FOLDER, "pack_icon.png")
                    tmp_fixed_dir = ".temp_icon_fixed"
                    tmp_fixed = os.path.join(tmp_fixed_dir, "pack_icon.png")
                    ok = ensure_and_fix_pack_icon(logo, tmp_fixed)
                    if ok or os.path.exists(tmp_fixed):
                        os.makedirs(os.path.dirname(dest_bp), exist_ok=True)
                        os.makedirs(os.path.dirname(dest_rp), exist_ok=True)
                        shutil.copy(tmp_fixed, dest_bp)
                        shutil.copy(tmp_fixed, dest_rp)
                    else:
                        shutil.copy(logo, dest_bp)
                        shutil.copy(logo, dest_rp)
                        print(" Copied pack icon without resizing (PIL not available)")
                    shutil.rmtree(".temp_logo_extract", ignore_errors=True)
                    shutil.rmtree(tmp_fixed_dir, ignore_errors=True)
                except Exception as e:
                    print(f" Failed to copy pack icon: {e}")
    with _logger.phase("Normalising RP assets", total=0, unit="step", colour="blue"):
        normalize_geometry_file_identifiers()
        sanitize_animation_keys_in_files()
        fix_animation_format_versions()
    with _logger.phase("Sweeping models → rp/geometry", total=0, unit="step", colour="blue"):
        normalise_all_geometry_to_geckolib(RP_FOLDER, namespace)
    with _logger.phase("Indexing RP assets", total=0, unit="step", colour="blue"):
        build_rp_asset_index()
    global _PORTING_NOTES
    _PORTING_NOTES = []
    stats = {
        "converted_entities_bp": [],
        "converted_entities_rp": [],
        "skipped_files":         [],
        "missing_geometry":      [],
        "errors":                [],
        "converted_items":       [],
        "converted_blocks":      [],
        "scripts_written":       [],
        "mixins_converted":      [],
    }
    with _logger.phase("Reading Java source", total=0, unit="file", colour="blue"):
        java_files = read_all_java_files(".")
        global _ALL_JAVA_FILES
        _ALL_JAVA_FILES = java_files
    with _logger.phase("Pre-scanning registries", total=0, unit="step", colour="blue"):
        detected_mod_id = run_prescan(java_files, namespace)
        if detected_mod_id and detected_mod_id != namespace:
            print(f"[prescan] mod_id → '{detected_mod_id}'")
            namespace = detected_mod_id
        build_renderer_entity_map()
    with _logger.phase("Converting LayerDefinition models", total=0, unit="step", colour="blue"):
        global _LAYERDEF_GEO_MAP
        _LAYERDEF_GEO_MAP = scan_and_convert_layerdefinition_models(java_files, namespace)
        if _LAYERDEF_GEO_MAP:
            geom_file_map, geom_ns_map = load_geometry_identifiers()
            build_rp_asset_index()
    with _logger.phase("Building asset maps", total=0, unit="step", colour="blue"):
        gecko_maps    = build_geckolib_mappings(".")
        geom_file_map, geom_ns_map = load_geometry_identifiers()
        anim_key_map  = load_animation_keys()
    total_files = len(java_files)
    with _logger.phase("Converting Java files", total=total_files, unit="file", colour="cyan") as bar:
        for path, code in java_files.items():
            fname  = os.path.basename(path)
            lname  = fname.lower()
            bar.set_postfix_str(fname[:38])
            try:
                cls_for_graph = extract_class_name(code)
                superchain = resolve_superchain(cls_for_graph) if cls_for_graph else []
                superchain_str = " ".join(superchain)

                fname_item_hint   = lname.endswith("item.java")  or "_item"  in lname
                fname_block_hint  = lname.endswith("block.java") or "_block" in lname
                fname_entity_hint = any(k in lname for k in ENTITY_OVERRIDE_KEYWORDS)
                fname_noise       = any(k in lname for k in NON_ENTITY_KEYWORDS) and not fname_entity_hint

                _ITEM_BASES = r'Item|SwordItem|PickaxeItem|ShovelItem|AxeItem|HoeItem|ArmorItem|BowItem|ShieldItem|FoodOnAStickItem|ThrowablePotionItem|TieredItem|DiggerItem|BlockItem|DoubleHighBlockItem|StandingAndWallBlockItem'
                _BLOCK_BASES = r'Block|BaseBlock|HalfTransparentBlock|BushBlock|FlowerBlock|SaplingBlock|CropBlock|TrapDoorBlock|DoorBlock|FenceBlock|WallBlock|StairBlock|SlabBlock|PressurePlateBlock|ButtonBlock|LeverBlock|TorchBlock|RedStoneWireBlock|ChestBlock|FurnaceBlock|LiquidBlock|GrassBlock|RotatedPillarBlock|HorizontalDirectionalBlock|DirectionalBlock'

                item_content_signals = [
                    bool(re.search(r'\bextends\s+(?:' + _ITEM_BASES + r')\b', code)),
                    bool(re.search(r'Item\.Properties\(\)|new\s+Item\.Properties\b|Item\.Properties\.of\b', code)),
                    bool(re.search(r'\.stacksTo\s*\(|\.durability\s*\(|FoodProperties\.Builder\b', code)),
                    bool(re.search(r'@Override\s+public\s+\w+\s+use\s*\(Level|InteractionResultHolder<ItemStack>', code)),
                    fname_item_hint,
                    bool(re.search(r'\b(?:' + _ITEM_BASES.replace('|', r'\b|\b') + r')\b', superchain_str)),
                ]
                is_item = sum(item_content_signals) >= 2 or (fname_item_hint and sum(item_content_signals) >= 1)
                block_content_signals = [
                    bool(re.search(r'\bextends\s+(?:' + _BLOCK_BASES + r')\b', code)),
                    bool(re.search(r'BlockBehaviour\.Properties|Block\.Properties\s*\.of\b|BlockBehaviour\.Properties\.of\b', code)),
                    bool(re.search(r'\.strength\s*\(|\.noCollission\s*\(|\.lightLevel\s*\(|\.randomTicks\s*\(', code)),
                    bool(re.search(r'@Override\s+public\s+\w+\s+use\s*\(BlockState|getStateForPlacement\s*\(', code)),
                    fname_block_hint,
                    bool(re.search(r'\b(?:' + _BLOCK_BASES.replace('|', r'\b|\b') + r')\b', superchain_str)),
                ]
                is_block = sum(block_content_signals) >= 2 or (fname_block_hint and sum(block_content_signals) >= 1)
                entity_candidate = (
                    is_likely_entity(code, path)
                    and not (is_item  and not fname_entity_hint)
                    and not (is_block and not fname_entity_hint)
                    and not fname_noise
                )
                if is_item:
                    convert_java_item_full(code, path, namespace)
                    stats["converted_items"].append(path)
                if is_block:
                    convert_java_block_full(code, path, namespace)
                    stats["converted_blocks"].append(path)
                if entity_candidate:
                    cls = extract_class_name(code) or os.path.splitext(fname)[0]
                    if cls and cls in ENTITY_REGISTRY:
                        entity_identifier = ENTITY_REGISTRY[cls]
                    else:
                        reg_name = None
                        for reg_pat in [
                            r'setRegistryName\s*\(\s*["\']([a-z0-9_:-]+)["\']',
                            r'\.register\s*\(\s*["\']([a-z0-9_]+)["\']\s*,\s*[^;]*?' + re.escape(cls or "") + r'::new',
                            r'EntityType\.Builder[^;]*\.build\s*\(\s*["\']([a-z0-9_]+)["\']',
                        ]:
                            m = re.search(reg_pat, code, re.I | re.DOTALL)
                            if m:
                                raw = m.group(1)
                                reg_name = raw if ":" in raw else f"{namespace}:{raw}"
                                break
                        entity_identifier = reg_name or f"{namespace}:{sanitize_identifier(cls)}"
                    convert_java_to_bedrock(path, entity_identifier, gecko_maps, geom_file_map, geom_ns_map, anim_key_map, stats)
            except Exception as e:
                print(f" Error processing {fname}: {e}")
                stats["errors"].append(f"{path}: {e}")
            finally:
                bar.update(1)
    with _logger.phase("Writing registries & lang", total=0, unit="step", colour="blue"):
        generate_texture_registry(pack_display_name)
        generate_sounds_registry(namespace)
        convert_lang_files()
    with _logger.phase("Scanning mixins", total=0, unit="step", colour="magenta"):
        scan_mixins(java_files, namespace)
    with _logger.phase("Scanning capabilities", total=0, unit="step", colour="magenta"):
        scan_capabilities(java_files, namespace)
    with _logger.phase("Scanning networking", total=0, unit="step", colour="magenta"):
        scan_networking(java_files, namespace)
    with _logger.phase("Scanning client-only classes", total=0, unit="step", colour="magenta"):
        scan_client_classes(java_files)
    with _logger.phase("Writing Global Cap Registry", total=0, unit="step", colour="green"):
        GlobalCapabilityRegistry.write(namespace, BP_FOLDER)
        GlobalCapabilityRegistry.ensure_import_in_main(BP_FOLDER)
    with _logger.phase("Scanning GUI / Screen classes", total=0, unit="step", colour="cyan"):
        for _gui_path, _gui_code in java_files.items():
            JavaGUIConverter.process(_gui_code, namespace, RP_FOLDER,
                                     os.path.join(BP_FOLDER, "scripts"))
    with _logger.phase("Scanning NBT serializers", total=0, unit="step", colour="cyan"):
        for _nbt_path, _nbt_code in java_files.items():
            _nbt_cls = extract_class_name(_nbt_code)
            if _nbt_cls and re.search(
                r'addAdditionalSaveData|readAdditionalSaveData', _nbt_code
            ):
                _nbt_id = f'{namespace}:{sanitize_identifier(_nbt_cls)}'
                RecursiveNBTSerializer.scan_and_emit_nbt_scripts(
                    _nbt_code, _nbt_id, namespace, BP_FOLDER)
    if jar_path:
        with _logger.phase("Processing loot / recipes / tags", total=0, unit="step", colour="blue"):
            process_loot_tables_from_jar(jar_path, namespace)
            process_recipes_from_jar(jar_path, namespace)
            extract_item_tags_from_jar(jar_path, namespace)
        with _logger.phase("Converting structures", total=0, unit="step", colour="blue"):
            process_structures_from_jar(jar_path, namespace, java_files=java_files)
    with _logger.phase("Writing manifests", total=0, unit="step", colour="blue"):
        write_manifest_for(BP_FOLDER, pack_display_name, "BP")
        write_manifest_for(RP_FOLDER, pack_display_name, "RP")
    with _logger.phase("Writing porting notes", total=0, unit="step", colour="yellow"):
        write_porting_notes()
    validation_warnings = []
    with _logger.phase("Validating output", total=0, unit="step", colour="blue"):
        validation_warnings = run_validation_pass()
    loot_dir   = os.path.join(BP_FOLDER, "loot_tables", "entities")
    loot_count = len(os.listdir(loot_dir)) if os.path.isdir(loot_dir) else 0
    recipe_dir   = os.path.join(BP_FOLDER, "recipes")
    recipe_count = len(os.listdir(recipe_dir)) if os.path.isdir(recipe_dir) else 0
    spawn_dir   = os.path.join(BP_FOLDER, "spawn_rules")
    spawn_count = len(os.listdir(spawn_dir)) if os.path.isdir(spawn_dir) else 0
    struct_dir  = os.path.join(BP_FOLDER, "structures")
    struct_count = len([f for f in os.listdir(struct_dir) if f.endswith(".mcstructure")]) if os.path.isdir(struct_dir) else 0
    feat_count  = len(os.listdir(os.path.join(BP_FOLDER, "features"))) if os.path.isdir(os.path.join(BP_FOLDER, "features")) else 0
    _orig("")
    _orig("  ")
    _orig("           ModMorpher — Conversion Done     ")
    _orig("  ")
    _orig(f"    BP entities   {len(stats['converted_entities_bp']):>4}                        ")
    _orig(f"    RP entities   {len(stats['converted_entities_rp']):>4}                        ")
    _orig(f"    Items         {len(stats['converted_items']):>4}                        ")
    _orig(f"    Blocks        {len(stats['converted_blocks']):>4}                        ")
    _orig(f"    Loot tables   {loot_count:>4}                        ")
    _orig(f"    Recipes       {recipe_count:>4}                        ")
    _orig(f"    Spawn rules   {spawn_count:>4}                        ")
    if struct_count:
        _orig(f"    Structures    {struct_count:>4}  ({feat_count} feature JSONs)   ")
    scripts_dir = os.path.join(BP_FOLDER, "scripts")
    script_count = len([f for f in os.listdir(scripts_dir) if f.endswith(".js") and f != "main.js"]) if os.path.isdir(scripts_dir) else 0
    if script_count:
        _orig(f"    Scripts       {script_count:>4}                        ")
    if _PORTING_NOTES:
        _orig(f"    Manual items  {len(_PORTING_NOTES):>4}  (see PORTING_NOTES.txt) ")
    gui_dir = os.path.join(RP_FOLDER, "ui")
    gui_count = len([f for f in os.listdir(gui_dir) if f.endswith(".json")]) if os.path.isdir(gui_dir) else 0
    if gui_count:
        _orig(f"    GUI screens   {gui_count:>4}  (controls + grid JSON)  ")
    nbt_scripts = [f for f in (os.listdir(os.path.join(BP_FOLDER,"scripts")) if os.path.isdir(os.path.join(BP_FOLDER,"scripts")) else []) if f.endswith("_nbt.js")]
    if nbt_scripts:
        _orig(f"    NBT scripts   {len(nbt_scripts):>4}  (recursive serializers) ")
    _orig("  ")
    if stats["missing_geometry"]:
        _orig(f"\n    {len(stats['missing_geometry'])} entity/entities using placeholder geometry:")
        for j, ent in stats["missing_geometry"][:20]:
            _orig(f"       {ent}  ← needs .geo.json")
    if stats["errors"]:
        _orig(f"\n    {len(stats['errors'])} error(s) during conversion:")
        for e in stats["errors"][:10]:
            _orig(f"       {e}")
    if validation_warnings:
        _orig(f"\n    {len(validation_warnings)} validation warning(s):")
        for w in validation_warnings[:20]:
            _orig(f"      {w}")
    else:
        _orig("\n    Validation passed — no broken references")
    _orig("")
    shutil.make_archive("Bedrock_Pack", "zip", "Bedrock_Pack")
    shutil.move("Bedrock_Pack.zip", "Bedrock_Pack.mcaddon")
    current_dir = os.getcwd()
    for item in os.listdir(current_dir):
        if os.path.isdir(item) and item.startswith("src"):
            try:
                print(f"Deleting: {item}")
                shutil.rmtree(item)
            except Exception as e:
                print(f"Failed to delete {item}: {e}")





Tool_Version = "1.5.0-upgraded"

def _strip_java_comments(src: str) -> str:

    out = []
    i = 0
    n = len(src)
    in_line = in_block = False
    in_str = False
    str_ch = ''
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ''
        if in_line:
            if ch in '\r\n':
                in_line = False
                out.append(ch)
            i += 1
            continue
        if in_block:
            if ch == '*' and nxt == '/':
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if in_str:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == str_ch:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_ch = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and nxt == '/':
            in_line = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            in_block = True
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def _safe_split_args(arg_text: str) -> list[str]:
    args, buf = [], []
    depth = 0
    in_str = False
    str_ch = ''
    esc = False
    for ch in arg_text or '':
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == str_ch:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            str_ch = ch
            buf.append(ch)
            continue
        if ch in '([{<':
            depth += 1
        elif ch in ')]}>':
            depth = max(0, depth - 1)
        if ch == ',' and depth == 0:
            piece = ''.join(buf).strip()
            if piece:
                args.append(piece)
            buf = []
        else:
            buf.append(ch)
    tail = ''.join(buf).strip()
    if tail:
        args.append(tail)
    return args


def _find_matching_brace(src: str, open_index: int) -> int:
    depth = 0
    in_str = False
    str_ch = ''
    esc = False
    for i in range(open_index, len(src)):
        ch = src[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == str_ch:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            str_ch = ch
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_method_body(source: str, method_name: str) -> Optional[str]:

    if not source:
        return None
    cleaned = _strip_java_comments(source)


    sig_re = re.compile(
        r'(?:@[\w.]+\s*(?:\([^)]*\)\s*)*)*'
        r'(?:public|protected|private|static|final|native|synchronized|abstract|\s)+'
        r'[\w<>\[\].?,\s]+\s+' + re.escape(method_name) + r'\s*\((?P<params>[^)]*)\)\s*(?:throws\s+[^{]+)?\{',
        re.MULTILINE
    )
    m = sig_re.search(cleaned)
    if not m:

        name_m = re.search(rf'\b{re.escape(method_name)}\s*\(', cleaned)
        if not name_m:
            return None
        brace = cleaned.find('{', name_m.end())
        if brace == -1:
            return None
        end = _find_matching_brace(cleaned, brace)
        return cleaned[brace + 1:end].strip() if end != -1 else cleaned[brace + 1:].strip()

    brace = cleaned.find('{', m.end() - 1)
    if brace == -1:
        return None
    end = _find_matching_brace(cleaned, brace)
    if end == -1:
        return cleaned[brace + 1:].strip()
    return cleaned[brace + 1:end].strip()


def _extract_class_name(source: str) -> Optional[str]:
    if not source:
        return None

    try:
        if JAVALANG_AVAILABLE:
            tree = javalang.parse.parse(source)
            for _, node in tree:
                if isinstance(node, (javalang.tree.ClassDeclaration,
                                     javalang.tree.InterfaceDeclaration,
                                     javalang.tree.EnumDeclaration,
                                     javalang.tree.RecordDeclaration)):
                    return node.name
    except Exception:
        pass
    m = re.search(r'\bclass\s+(\w+)', source)
    if m:
        return m.group(1)
    m = re.search(r'\binterface\s+(\w+)', source)
    if m:
        return m.group(1)
    m = re.search(r'\benum\s+(\w+)', source)
    if m:
        return m.group(1)
    m = re.search(r'\brecord\s+(\w+)', source)
    if m:
        return m.group(1)
    return None


def _normalize_generic_type_name(type_name: Optional[str]) -> Optional[str]:
    if not type_name:
        return None
    t = str(type_name).strip()
    t = re.sub(r'<.*>', '', t)
    t = t.replace('final ', '').replace('volatile ', '').replace('transient ', '')
    t = t.split('.')[-1]
    return t.strip()


class JavaAST:




    def __init__(self, source: str):
        self._src = source or ''
        self._clean = _strip_java_comments(self._src)
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

    def primary_class_name(self) -> Optional[str]:
        self._parse()
        if self._tree:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                return node.name
            for _, node in self._tree.filter(javalang.tree.InterfaceDeclaration):
                return node.name
            for _, node in self._tree.filter(javalang.tree.EnumDeclaration):
                return node.name
        return _extract_class_name(self._src)

    def get_class_declarations(self) -> List:
        self._parse()
        if not self._tree:
            return []
        return [node for _, node in self._tree.filter(javalang.tree.ClassDeclaration)]

    def all_class_names(self) -> List[str]:
        names = []
        self._parse()
        if self._tree:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                names.append(node.name)
            for _, node in self._tree.filter(javalang.tree.InterfaceDeclaration):
                names.append(node.name)
            for _, node in self._tree.filter(javalang.tree.EnumDeclaration):
                names.append(node.name)
        else:
            for m in re.finditer(r'\b(?:class|interface|enum|record)\s+(\w+)', self._src):
                names.append(m.group(1))
        return list(dict.fromkeys(names))

    def superclass_name(self, cls_name: Optional[str] = None) -> Optional[str]:
        self._parse()
        if self._tree:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                if cls_name and node.name != cls_name:
                    continue
                if node.extends and hasattr(node.extends, 'name'):
                    return node.extends.name
        m = re.search(rf'\bclass\s+{re.escape(cls_name or "")}\b[^\{{}}]*\bextends\s+(\w+)', self._src) if cls_name else None
        if m:
            return m.group(1)
        return None

    def implemented_interfaces(self, cls_name: Optional[str] = None) -> List[str]:
        self._parse()
        if self._tree:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                if cls_name and node.name != cls_name:
                    continue
                if node.implements:
                    return [i.name for i in node.implements if hasattr(i, 'name')]
        return []

    def class_extends(self, target_name: str, cls_name: Optional[str] = None) -> bool:
        self._parse()
        if self._tree:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                if cls_name and node.name != cls_name:
                    continue
                if node.extends and hasattr(node.extends, 'name') and node.extends.name == target_name:
                    return True
        if cls_name:
            pat = rf'\bclass\s+{re.escape(cls_name)}\b[\s\S]*?\bextends\s+{re.escape(target_name)}\b'
            return bool(re.search(pat, self._src))
        return False

    def annotation_value(self, annotation_name: str) -> Optional[str]:
        self._parse()
        if self._tree:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                for ann in node.annotations or []:
                    if ann.name == annotation_name:
                        elem = getattr(ann, 'element', None)
                        if elem is not None and hasattr(elem, 'value'):
                            v = elem.value
                            return v.strip('"').strip("'") if isinstance(v, str) else str(v)
        m = re.search(rf'@{re.escape(annotation_name)}(?:\(([^)]*)\))?', self._src)
        if m and m.group(1):
            return m.group(1)
        return None

    def field_string_values(self, field_names: Set[str]) -> Dict[str, str]:
        self._parse()
        results = {}
        if self._tree:
            for _, node in self._tree.filter(javalang.tree.FieldDeclaration):
                for decl in node.declarators:
                    if decl.name in field_names and decl.initializer:
                        init = decl.initializer
                        if isinstance(init, javalang.tree.Literal) and init.value:
                            results[decl.name] = init.value.strip('"').strip("'")
        else:
            for name in field_names:
                m = re.search(rf'\b{name}\b\s*=\s*"(.*?)"', self._src, re.DOTALL)
                if m:
                    results[name] = m.group(1)
        return results

    def all_string_literals(self) -> List[str]:
        self._parse()
        if self._tree:
            out = []
            for _, node in self._tree.filter(javalang.tree.Literal):
                if node.value and node.value.startswith('"'):
                    out.append(node.value.strip('"'))
            return out
        return re.findall(r'"((?:[^"\\]|\\.)*)"', self._src)

    def method_names(self) -> Set[str]:
        self._parse()
        if self._tree:
            return {node.name for _, node in self._tree.filter(javalang.tree.MethodDeclaration)}
        return set(re.findall(r'\b(?:public|protected|private|static|final|native|synchronized|\s)+[\w<>\[\].?,\s]+\s+(\w+)\s*\(', self._src))

    def invocations_of(self, method_name: str) -> List:
        self._parse()
        if self._tree:
            return [node for _, node in self._tree.filter(javalang.tree.MethodInvocation) if node.member == method_name]
        return re.findall(rf'\b{re.escape(method_name)}\s*\(', self._src)

    def object_creations_of(self, class_name: str) -> List:
        self._parse()
        if self._tree:
            return [node for _, node in self._tree.filter(javalang.tree.ClassCreator) if hasattr(node.type, 'name') and node.type.name == class_name]
        return re.findall(rf'new\s+{re.escape(class_name)}\s*\(', self._src)

    def all_object_creation_types(self) -> List[str]:
        self._parse()
        if self._tree:
            return [node.type.name for _, node in self._tree.filter(javalang.tree.ClassCreator) if hasattr(node.type, 'name')]
        return [m.group(1) for m in re.finditer(r'new\s+([A-Z]\w*)\s*\(', self._src)]

    def method_body_source(self, method_name: str) -> Optional[str]:
        body = _extract_method_body(self._src, method_name)
        return body

    def instanceof_types(self) -> Set[str]:
        self._parse()
        if self._tree:
            types = set()
            for _, node in self._tree.filter(javalang.tree.BinaryOperation):
                if node.operator == 'instanceof' and hasattr(node.operandr, 'name'):
                    types.add(node.operandr.name)
            return types
        return set(re.findall(r'instanceof\s+(\w+)', self._src))

    @staticmethod
    def strip_generics(name: str) -> str:
        return _normalize_generic_type_name(name) or name

    @staticmethod
    def first_string_arg(invocation_node) -> Optional[str]:
        args = getattr(invocation_node, 'arguments', None) or []
        for arg in args:
            if isinstance(arg, javalang.tree.Literal) and arg.value and arg.value.startswith('"'):
                return arg.value.strip('"')
        return None

    @staticmethod
    def translate_java_body_to_js(java_body: str, event_type: str, param: str, namespace: str, safe_name: str) -> list:
        if not java_body:
            return []
        try:
            if JAVALANG_AVAILABLE:
                dummy_code = f"""
public class Dummy {{
    public void dummy() {{
        {java_body}
    }}
}}
"""
                tree = javalang.parse.parse(dummy_code)
                lines = []
                player = _get_player_var(event_type, param)
                for _, node in tree.filter(javalang.tree.MethodDeclaration):
                    if node.name == 'dummy':
                        for stmt in node.body or []:
                            lines.extend(translate_statement(stmt, player, namespace, JavaSymbolTable()))
                        return lines
        except Exception:
            pass

        lines = [f'// Fallback translation for {safe_name}']
        for raw_line in java_body.splitlines():
            if raw_line.strip():
                lines.append(f'// {raw_line.rstrip()}')
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
            'sendMessage': '{0}.sendMessage({1})',
            'getHealth': '{0}.getComponent("minecraft:health").currentValue',
            'setHealth': '{0}.getComponent("minecraft:health").setCurrentValue({1})',
            'getMaxHealth': '{0}.getComponent("minecraft:health").maxValue',
            'getInventory': '{0}.getComponent("minecraft:inventory").container',
            'addItem': '{0}.getComponent("minecraft:inventory").container.addItem({1})',
            'removeItem': '{0}.getComponent("minecraft:inventory").container.removeItem({1})',
            'getLevel': '{0}.dimension',
            'getPosition': '{0}.location',
            'setPosition': '{0}.teleport({1})',
            'isCreative': '({0}.gameMode === GameMode.creative)',
            'isSpectator': '({0}.gameMode === GameMode.spectator)',
            'isSprinting': '{0}.isSprinting',
            'isOnGround': '{0}.isOnGround',
            'getExperiencePoints': '{0}.getTotalXp()',
            'addExperiencePoints': '{0}.addExperience({1})',
            'hurt': '{0}.applyDamage({1})',
            'heal': '{0}.getComponent("minecraft:health").setCurrentValue({0}.getComponent("minecraft:health").currentValue + {1})',
            'getEffect': '{0}.getEffect("{1}")',
            'addEffect': '{0}.addEffect("{1}", {2}, {{ duration: {3} }})',
            'removeEffect': '{0}.removeEffect("{1}")',
            'getName': '{0}.nameTag',
            'runCommand': '{0}.runCommand("{1}")',
            'runCommandAsync': '{0}.runCommandAsync("{1}")',
        },
        'Entity': {
            'getHealth': '{0}.getComponent("minecraft:health").currentValue',
            'setHealth': '{0}.getComponent("minecraft:health").setCurrentValue({1})',
            'getMaxHealth': '{0}.getComponent("minecraft:health").maxValue',
            'getPosition': '{0}.location',
            'setPosition': '{0}.teleport({1})',
            'getVelocity': '{0}.getVelocity()',
            'setVelocity': '{0}.applyImpulse({1})',
            'kill': '{0}.kill()',
            'remove': '{0}.remove()',
            'hurt': '{0}.applyDamage({1})',
            'isAlive': '(!{0}.isRemoved())',
            'getType': '{0}.typeId',
            'getTags': '{0}.getTags()',
            'hasTag': '{0}.hasTag({1})',
            'addTag': '{0}.addTag({1})',
            'removeTag': '{0}.removeTag({1})',
            'getLevel': '{0}.dimension',
            'getCustomName': '{0}.nameTag',
            'setCustomName': '{0}.nameTag = {1}',
            'runCommand': '{0}.runCommand("{1}")',
            'runCommandAsync': '{0}.runCommandAsync("{1}")',
        },
        'ItemStack': {
            'getCount': '{0}.amount',
            'setCount': '{0}.amount = {1}',
            'grow': '{0}.amount += {1}',
            'shrink': '{0}.amount -= {1}',
            'isEmpty': '({0}.amount <= 0)',
            'getItem': '{0}.typeId',
            'getMaxStackSize': '{0}.maxAmount',
            'copy': 'new ItemStack({0}.typeId, {0}.amount)',
            'getDamageValue': '{0}.getComponent("minecraft:durability").damage',
            'setDamageValue': '{0}.getComponent("minecraft:durability").damage = {1}',
            'getDisplayName': '({0}.nameTag ?? {0}.typeId)',
            'setCustomName': '{0}.nameTag = {1}',
        },
        'Dimension': {
            'setBlockState': '{0}.getBlock({1}).setPermutation({2})',
            'getBlockState': '{0}.getBlock({1}).permutation',
            'getBlockEntity': '{0}.getBlock({1})',
            'addParticle': '{0}.spawnParticle({1}, {2})',
            'playSound': '{0}.playSound("{1}", {2})',
            'getEntitiesOfClass': '[...{0}.getEntities({{ type: "{1}" }})]',
            'getClosestPlayer': '{0}.getPlayers()[0]',
            'spawnEntity': '{0}.spawnEntity({1}, {2})',
            'runCommand': '{0}.runCommand("{1}")',
        },
        'DynamicProperties': {
            'getInt': '({0}.getDynamicProperty({1}) ?? 0)',
            'putInt': '{0}.setDynamicProperty({1}, {2})',
            'getFloat': '({0}.getDynamicProperty({1}) ?? 0.0)',
            'putFloat': '{0}.setDynamicProperty({1}, {2})',
            'getBoolean': '({0}.getDynamicProperty({1}) ?? false)',
            'putBoolean': '{0}.setDynamicProperty({1}, {2})',
            'getString': '({0}.getDynamicProperty({1}) ?? "")',
            'putString': '{0}.setDynamicProperty({1}, {2})',
            'hasKey': '({0}.getDynamicProperty({1}) !== undefined)',
            'contains': '({0}.getDynamicProperty({1}) !== undefined)',
            'remove': '{0}.setDynamicProperty({1}, undefined)',
            'getCompound': 'JSON.parse({0}.getDynamicProperty({1}) ?? "{}")',
            'put': '{0}.setDynamicProperty({1}, JSON.stringify({2}))',
        },
        'Container': {
            'getItem': '{0}.getItem({1})',
            'setItem': '{0}.setItem({1}, {2})',
            'getContainerSize': '{0}.size',
            'addItem': '{0}.addItem({1})',
        },
        'Vector3': {
            'add': '{{ x: {0}.x+{1}.x, y: {0}.y+{1}.y, z: {0}.z+{1}.z }}',
            'subtract': '{{ x: {0}.x-{1}.x, y: {0}.y-{1}.y, z: {0}.z-{1}.z }}',
            'scale': '{{ x: {0}.x*{1}, y: {0}.y*{1}, z: {0}.z*{1} }}',
            'length': 'Math.sqrt({0}.x**2+{0}.y**2+{0}.z**2)',
            'distanceTo': 'Math.sqrt(({0}.x-{1}.x)**2+({0}.y-{1}.y)**2+({0}.z-{1}.z)**2)',
        },
    }

    _CAP_ENERGY = {'receiveEnergy', 'extractEnergy', 'getEnergyStored', 'getMaxEnergyStored', 'canReceive', 'canExtract'}
    _CAP_FLUID = {'fill', 'drain', 'getFluidAmount', 'getTankCapacity', 'getFluidInTank', 'getTanks', 'isFluidValid'}
    _CAP_ITEM_HDL = {'insertItem', 'extractItem', 'getStackInSlot', 'getSlots', 'isItemValid', 'getSlotLimit'}
    _CAP_ITEMSTACK = {'getCount', 'setCount', 'grow', 'shrink', 'isEmpty'}

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
        self._qualifier_type_cache[var_name] = self._resolve_bedrock_type(var_type) or self._qualifier_type_cache.get(var_name, '')

    def get_variable_type(self, var_name: str) -> Optional[str]:
        return self.variables.get(var_name)

    def _resolve_bedrock_type(self, java_type: str) -> Optional[str]:
        base = _normalize_generic_type_name(java_type) or java_type
        return self.JAVA_TYPE_TO_BEDROCK.get(base)

    def get_bedrock_type_for_var(self, var_name: str) -> Optional[str]:
        if var_name in self._qualifier_type_cache and self._qualifier_type_cache[var_name]:
            return self._qualifier_type_cache[var_name]
        lower = var_name.lower()
        if lower in ('player', 'p', 'serverplayer', 'localplayer'):
            return 'Player'
        if lower in ('entity', 'mob', 'e', 'target', 'attacker', 'victim'):
            return 'Entity'
        if lower in ('stack', 'itemstack', 'item', 'helditem', 'mainhand', 'offhand'):
            return 'ItemStack'
        if lower in ('level', 'world', 'dimension', 'serverlevel', 'dim'):
            return 'Dimension'
        if lower in ('nbt', 'tag', 'compound', 'data', 'persistentdata'):
            return 'DynamicProperties'
        if lower in ('pos', 'blockpos', 'position', 'origin', 'loc', 'location'):
            return 'Vector3'
        if lower in ('inventory', 'container', 'inv', 'chest', 'slots'):
            return 'Container'
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
        if method_name in self._CAP_ENERGY:
            return 'energy'
        if method_name in self._CAP_FLUID:
            return 'fluid'
        if method_name in self._CAP_ITEM_HDL:
            return 'item_handler'
        if method_name in self._CAP_ITEMSTACK:
            return 'itemstack'
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
                        ret_type = getattr(method.return_type, 'name', 'void') if method.return_type else 'void'
                        params = {}
                        for p in (method.parameters or []):
                            ptype = getattr(p.type, 'name', str(p.type))
                            params[p.name] = ptype
                            self.set_variable_type(p.name, ptype)
                        self.register_method(node.name, method.name, ret_type, params)
                    for field in node.fields:
                        ftype = getattr(field.type, 'name', str(field.type))
                        for decl in field.declarators:
                            self.register_field(node.name, decl.name, ftype)
                            self.set_variable_type(decl.name, ftype)
                elif isinstance(node, javalang.tree.LocalVariableDeclaration):
                    ltype = getattr(node.type, 'name', str(node.type))
                    for decl in node.declarators:
                        self.set_variable_type(decl.name, ltype)
        except Exception:
            self._scan_regex(java_code)

    def _scan_regex(self, java_code: str):
        code = _strip_java_comments(java_code)
        for m in re.finditer(r'\bclass\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w\s,<>.]+))?', code):
            interfaces = [x.strip().split('<', 1)[0] for x in (m.group(3) or '').split(',') if x.strip()]
            self.register_class(m.group(1), m.group(2), interfaces)
        for m in re.finditer(r'(?:private|protected|public|final|static)\s+(?:final\s+)?([\w<>\[\].?,]+)\s+(\w+)\s*[=;]', code):
            self.set_variable_type(m.group(2), m.group(1))
        for m in re.finditer(r'(?:void|\w+)\s+\w+\s*\(([^)]*)\)', code):
            for param in _safe_split_args(m.group(1)):
                parts = param.strip().split()
                if len(parts) >= 2:
                    self.set_variable_type(parts[-1].strip(), parts[-2].strip())


def _expr_to_js_text(expr: object, symbol_table: Optional[JavaSymbolTable] = None) -> Optional[str]:
    if expr is None:
        return None

    if JAVALANG_AVAILABLE:
        if isinstance(expr, javalang.tree.Literal):
            return str(expr.value)
        if isinstance(expr, javalang.tree.MemberReference):
            qual = getattr(expr, 'qualifier', None)
            if qual:
                return f'{qual}.{expr.member}'
            return expr.member
        if isinstance(expr, javalang.tree.MethodInvocation):
            member = getattr(expr, 'member', '')
            qual = getattr(expr, 'qualifier', None)
            args = [translate_expression(a, symbol_table) for a in (getattr(expr, 'arguments', None) or [])]
            args = [a for a in args if a is not None]
            call = f'{member}({", ".join(args)})'
            if qual:
                return f'{qual}.{call}'
            return call
        if isinstance(expr, javalang.tree.BinaryOperation):
            left = translate_expression(expr.operandl, symbol_table)
            right = translate_expression(expr.operandr, symbol_table)
            if left is not None and right is not None:
                return f'({left} {expr.operator} {right})'
        if isinstance(expr, javalang.tree.TernaryExpression):
            cond = translate_expression(expr.condition, symbol_table)
            t = translate_expression(expr.if_true, symbol_table)
            f = translate_expression(expr.if_false, symbol_table)
            if None not in (cond, t, f):
                return f'({cond} ? {t} : {f})'
        if isinstance(expr, javalang.tree.Cast):
            return translate_expression(expr.expression, symbol_table)
        if isinstance(expr, javalang.tree.This):
            return 'this'
        if isinstance(expr, javalang.tree.ClassCreator):
            tname = getattr(expr.type, 'name', 'Object')
            args = [translate_expression(a, symbol_table) for a in (expr.arguments or [])]
            args = [a for a in args if a is not None]
            return f'new {tname}({", ".join(args)})'
        if isinstance(expr, javalang.tree.ArrayCreator):
            return '[]'
        if isinstance(expr, javalang.tree.UnaryOperation):
            operand = translate_expression(expr.expression, symbol_table)
            if operand is not None:
                return f'({expr.operator}{operand})'


    s = str(expr)
    s = s.replace('true', 'true').replace('false', 'false')
    return s


def translate_expression(expr: object, symbol_table: Optional[JavaSymbolTable] = None) -> Optional[str]:
    if expr is None:
        return None
    try:
        if JAVALANG_AVAILABLE:
            return _expr_to_js_text(expr, symbol_table)
    except Exception:
        pass
    return _expr_to_js_text(expr, symbol_table)


def _translate_block_stmt_list(stmts, player: str, namespace: str, symbol_table: Optional[JavaSymbolTable]) -> list[str]:
    out: list[str] = []
    for s in stmts or []:
        out.extend(translate_statement(s, player, namespace, symbol_table))
    return out


def translate_statement(stmt: object, player: str, namespace: str, symbol_table: Optional[JavaSymbolTable] = None) -> list:
    symbol_table = symbol_table or JavaSymbolTable()
    if stmt is None:
        return []

    if JAVALANG_AVAILABLE:
        try:
            if isinstance(stmt, javalang.tree.BlockStatement):
                inner = getattr(stmt, 'statements', None) or []
                return _translate_block_stmt_list(inner, player, namespace, symbol_table)

            if isinstance(stmt, javalang.tree.StatementExpression):
                expr = stmt.expression
                if isinstance(expr, javalang.tree.MethodInvocation):
                    js_line = translate_method_invocation(expr, player, namespace, symbol_table)
                    return [js_line] if js_line else []
                if isinstance(expr, javalang.tree.Assignment):
                    left = translate_expression(expr.expressionl, symbol_table)
                    right = translate_expression(expr.value, symbol_table)
                    if left and right:
                        return [f'    {left} = {right};']
                return [f'    // unsupported expression: {translate_expression(expr, symbol_table)}']

            if isinstance(stmt, javalang.tree.LocalVariableDeclaration):
                js_type = 'let'
                if getattr(stmt, 'final', False):
                    js_type = 'const'
                lines = []
                for decl in stmt.declarators:
                    init = ''
                    if decl.initializer:
                        init_val = translate_expression(decl.initializer, symbol_table)
                        if init_val:
                            init = f' = {init_val}'
                    lines.append(f'    {js_type} {decl.name}{init};')
                return lines

            if isinstance(stmt, javalang.tree.IfStatement):
                condition = translate_expression(stmt.condition, symbol_table)
                lines = [f'    if ({condition or "true"}) {{']
                lines.extend(_translate_block_stmt_list(
                    getattr(stmt.then_statement, 'statements', None) if isinstance(stmt.then_statement, javalang.tree.BlockStatement) else ([stmt.then_statement] if stmt.then_statement else []),
                    player, namespace, symbol_table
                ))
                lines.append('    }')
                if stmt.else_statement:
                    lines.append('    else {')
                    lines.extend(_translate_block_stmt_list(
                        getattr(stmt.else_statement, 'statements', None) if isinstance(stmt.else_statement, javalang.tree.BlockStatement) else ([stmt.else_statement] if stmt.else_statement else []),
                        player, namespace, symbol_table
                    ))
                    lines.append('    }')
                return lines

            if isinstance(stmt, javalang.tree.ReturnStatement):
                if stmt.expression:
                    expr = translate_expression(stmt.expression, symbol_table)
                    return [f'    return {expr};'] if expr else ['    return;']
                return ['    return;']

            if isinstance(stmt, javalang.tree.ForStatement):

                header = 'for (...)'
                lines = [f'    // {header}']
                body = getattr(stmt, 'body', None)
                body_list = body if isinstance(body, list) else ([body] if body else [])
                lines.extend(_translate_block_stmt_list(body_list, player, namespace, symbol_table))
                return lines

            if isinstance(stmt, javalang.tree.WhileStatement):
                cond = translate_expression(stmt.condition, symbol_table)
                lines = [f'    while ({cond or "true"}) {{']
                body = getattr(stmt.body, 'statements', None) if isinstance(stmt.body, javalang.tree.BlockStatement) else ([stmt.body] if stmt.body else [])
                lines.extend(_translate_block_stmt_list(body, player, namespace, symbol_table))
                lines.append('    }')
                return lines

            if isinstance(stmt, javalang.tree.DoStatement):
                cond = translate_expression(stmt.condition, symbol_table)
                lines = ['    do {']
                body = getattr(stmt.body, 'statements', None) if isinstance(stmt.body, javalang.tree.BlockStatement) else ([stmt.body] if stmt.body else [])
                lines.extend(_translate_block_stmt_list(body, player, namespace, symbol_table))
                lines.append(f'    }} while ({cond or "true"});')
                return lines

            if isinstance(stmt, javalang.tree.BreakStatement):
                return ['    break;']

            if isinstance(stmt, javalang.tree.ContinueStatement):
                return ['    continue;']

            if isinstance(stmt, javalang.tree.ThrowStatement):
                expr = translate_expression(stmt.expression, symbol_table)
                fallback = 'new Error("translated throw")'
                return [f'    throw {expr or fallback};']

            if isinstance(stmt, javalang.tree.SwitchStatement):
                lines = [f'    switch ({translate_expression(stmt.expression, symbol_table) or "undefined"}) {{']
                for case in stmt.cases or []:
                    labels = case.case or []
                    if labels:
                        for label in labels:
                            lines.append(f'        case {translate_expression(label, symbol_table)}:')
                    else:
                        lines.append('        default:')
                    lines.extend(_translate_block_stmt_list(case.statements or [], player, namespace, symbol_table))
                    lines.append('            break;')
                lines.append('    }')
                return lines
        except Exception:
            pass


    raw = str(stmt).strip()
    return [f'    // {raw}'] if raw else []


def translate_method_invocation(invocation: object, player: str, namespace: str, symbol_table: JavaSymbolTable) -> Optional[str]:
    member = getattr(invocation, 'member', '') or ''
    qualifier = getattr(invocation, 'qualifier', None)
    if isinstance(qualifier, list) and len(qualifier) == 1:
        qualifier = qualifier[0]
    if not qualifier:
        qualifier = None
    args = getattr(invocation, 'arguments', []) or []


    if member in ('receiveEnergy', 'extractEnergy'):
        if args:
            amt = translate_expression(args[0], symbol_table) or '0'
            return f'    {member}({player}, {amt});'

    nbt_result = NBTTranslator.translate_nbt_call(member, args, namespace, player)
    if nbt_result:
        return nbt_result

    cap_type = symbol_table.method_belongs_to_capability(member)
    if cap_type:
        if cap_type == 'energy' and member == 'getEnergyStored':
            return f'({player}.getDynamicProperty("{namespace}:energy_stored") ?? 0)'
        if cap_type == 'fluid':
            if member == 'fill' and len(args) >= 2:
                fluid_stack = translate_expression(args[0], symbol_table) or 'null'
                amount = translate_expression(args[1], symbol_table) or '0'
                return f'    fill({player}, {fluid_stack}, {amount});'
            if member == 'drain' and args:
                amount = translate_expression(args[0], symbol_table) or '0'
                return f'    drain({player}, {amount});'
        if cap_type == 'item_handler':
            if member == 'insertItem' and len(args) >= 2:
                slot = translate_expression(args[0], symbol_table) or '0'
                stack = translate_expression(args[1], symbol_table) or 'null'
                return f'    insertItem({player}, {slot}, {stack});'
            if member == 'extractItem' and len(args) >= 2:
                slot = translate_expression(args[0], symbol_table) or '0'
                amount = translate_expression(args[1], symbol_table) or '1'
                return f'    extractItem({player}, {slot}, {amount});'


    if qualifier:
        btype = symbol_table.get_bedrock_type_for_var(qualifier)
        if btype:
            template = symbol_table.TYPE_METHOD_MAP.get(btype, {}).get(member)
            if template:
                translated_args = [translate_expression(a, symbol_table) or 'undefined' for a in args]
                result = template.replace('{0}', qualifier)
                for i, arg in enumerate(translated_args):
                    result = result.replace(f'{{{i + 1}}}', arg)
                return result


    bedrock_call = JavaToBedrockMethodMap.translate_method_call(member, args, qualifier)
    if bedrock_call:
        return bedrock_call


    translated_args = [translate_expression(a, symbol_table) or 'undefined' for a in args]
    if qualifier:
        return f'{qualifier}.{member}({", ".join(translated_args)})'
    return f'{member}({", ".join(translated_args)})'



JavaToBedrockMethodMap.STRICT_MAPPING.update({
    'world.getDimension': 'world.getDimension({0})',
    'world.getPlayers': 'world.getAllPlayers()',
    'world.sendMessage': 'world.sendMessage({0})',
    'world.playSound': 'world.playSound({0}, {1})',
    'world.spawnParticle': 'world.spawnParticle({0}, {1})',
    'dimension.getBlock': '{0}.getBlock({1})',
    'dimension.getEntities': '{0}.getEntities({1})',
    'dimension.spawnEntity': '{0}.spawnEntity({1}, {2})',
    'entity.getComponent': '{0}.getComponent({1})',
    'entity.getDynamicProperty': '{0}.getDynamicProperty({1})',
    'entity.setDynamicProperty': '{0}.setDynamicProperty({1}, {2})',
    'entity.getTags': '{0}.getTags()',
    'entity.hasTag': '{0}.hasTag({1})',
    'entity.addTag': '{0}.addTag({1})',
    'entity.removeTag': '{0}.removeTag({1})',
    'entity.teleport': '{0}.teleport({1})',
    'system.run': 'system.run({0})',
    'system.runInterval': 'system.runInterval({0}, {1})',
    'system.runTimeout': 'system.runTimeout({0}, {1})',
})


_MIXIN_TARGET_TO_BEDROCK.update({
    "AbstractBlock": ("afterEvents", "playerPlaceBlock", "event.block"),
    "Block": ("afterEvents", "playerPlaceBlock", "event.block"),
    "Item": ("afterEvents", "itemUse", "event"),
    "LivingEntity": ("afterEvents", "entityHurt", "event.hurtEntity"),
    "PlayerEntity": ("afterEvents", "playerInteractWithEntity", "event.player"),
    "ServerPlayerEntity": ("afterEvents", "playerInteractWithEntity", "event.player"),
})

_INJECT_HEAD_BEDROCK.update({
    "onUse": "world.afterEvents.itemUse",
    "use": "world.afterEvents.itemUse",
    "appendTooltip": "world.afterEvents.itemUse",
    "inventoryTick": "world.afterEvents.entitySpawn",
    "tick": "world.afterEvents.entitySpawn",
    "onEntityHit": "world.afterEvents.entityHitEntity",
    "onBlockBreakStart": "world.afterEvents.playerBreakBlock",
    "onBlockBreakEnd": "world.afterEvents.playerBreakBlock",
})

def _mixin_target_name(code: str) -> Optional[str]:
    m = re.search(r'@Mixin\s*\(\s*(?:value\s*=\s*)?([A-Za-z_][\w$.]+)\.class', code)
    if m:
        return m.group(1).split('.')[-1]
    m = re.search(r'@Mixin\s*\(\s*"([^"]+)"\s*\)', code)
    if m:
        return m.group(1).split('.')[-1]
    return None

def _translate_use_body(body: str, namespace: str, safe_name: str) -> list[str]:
    if not body:
        return [f'    // TODO: translate {safe_name} manually']
    lines = []
    for raw in body.splitlines():
        raw = raw.rstrip()
        if not raw.strip():
            continue

        lines.append(f'    // {raw.strip()}')
    return lines

def scan_mixins(java_files: Dict[str, str], namespace: str) -> None:
    for path, code in java_files.items():
        if '@Mixin' not in code and 'org.spongepowered.asm.mixin' not in code:
            continue

        target_cls = _mixin_target_name(code) or extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
        cls_name = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
        safe_name = sanitize_identifier(cls_name)

        inject_methods = re.findall(
            r'@Inject\s*\([^)]*method\s*=\s*["\']([^"\']+)["\'][^)]*\)[^{]*'
            r'(?:public|private|protected)?[\s\S]*?\b(\w+)\s*\(',
            code, re.DOTALL
        )
        redirect_methods = re.findall(
            r'@Redirect\s*\([^)]*method\s*=\s*["\']([^"\']+)["\'][^)]*\)[^{]*'
            r'(?:public|private|protected)?[\s\S]*?\b(\w+)\s*\(',
            code, re.DOTALL
        )
        overwrite_methods = re.findall(
            r'@Overwrite[^{]*(?:public|private|protected)[\s\S]*?\b(\w+)\s*\(',
            code, re.DOTALL
        )

        bedrock_info = _MIXIN_TARGET_TO_BEDROCK.get(target_cls)
        if not bedrock_info and target_cls in _INHERITANCE_GRAPH:
            for ancestor in resolve_superchain(target_cls):
                if ancestor in _MIXIN_TARGET_TO_BEDROCK:
                    bedrock_info = _MIXIN_TARGET_TO_BEDROCK[ancestor]
                    break

        script_lines = [f'import {{ world, system }} from "@minecraft/server";', '']
        wrote_anything = False

        for target_method, handler_method in inject_methods:
            bedrock_event = _INJECT_HEAD_BEDROCK.get(target_method) or _INJECT_HEAD_BEDROCK.get(handler_method)
            if bedrock_event:
                body = _extract_method_body(code, handler_method)
                translated = _translate_use_body(body or '', namespace, safe_name)
                script_lines += [
                    f'// @Inject {target_method} -> {bedrock_event}',
                    f'{bedrock_event}.subscribe((event) => {{',
                ] + translated + ['});', '']
                wrote_anything = True
            else:
                _PORTING_NOTES.append(
                    f"[mixin] {cls_name}: @Inject on {target_cls}.{target_method}() has no automatic Bedrock mapping."
                )

        for target_method, handler_method in redirect_methods:
            _PORTING_NOTES.append(
                f"[mixin] {cls_name}: @Redirect on {target_cls}.{target_method}() cannot be translated automatically; rewrite as an event hook."
            )
            body = _extract_method_body(code, handler_method)
            if body:
                script_lines += [
                    f'// @Redirect {target_method} (manual port)',
                    f'// {body.replace(chr(10), chr(10) + "// ")}',
                    ''
                ]

        for method_name in overwrite_methods:
            body = _extract_method_body(code, method_name)
            bedrock_event = _INJECT_HEAD_BEDROCK.get(method_name)
            if bedrock_event and body:
                translated = _translate_use_body(body, namespace, safe_name)
                script_lines += [
                    f'// @Overwrite {method_name} -> {bedrock_event}',
                    f'{bedrock_event}.subscribe((event) => {{',
                ] + translated + ['});', '']
                wrote_anything = True
            else:
                _PORTING_NOTES.append(
                    f"[mixin] {cls_name}: @Overwrite of {target_cls}.{method_name}() has no automatic Bedrock mapping."
                )


        if 'fabric' in code.lower() or 'quilt' in code.lower():
            _PORTING_NOTES.append(
                f"[mixin] {cls_name}: Fabric/Quilt mixin detected. Bedrock equivalents are event-driven; manual refactor may be needed for call-site redirection."
            )

        if wrote_anything:
            out_path = os.path.join(BP_FOLDER, "scripts", f"mixin_{safe_name}.js")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(script_lines))
            print(f"[mixin] Wrote {out_path}")

def scan_fabric_quilt_mixins(java_files: Dict[str, str], namespace: str) -> None:

    return scan_mixins(java_files, namespace)



BEDROCK_API_IMPORTS = {
    'core': ['world', 'system', 'GameMode', 'MinecraftEffectTypes', 'MinecraftDimensionTypes'],
    'item': ['ItemStack', 'ItemTypes'],
    'block': ['BlockPermutation', 'BlockVolume'],
    'ui': ['ActionFormData', 'ModalFormData', 'MessageFormData'],
    'entity': ['Entity', 'Player'],
}

def generate_bedrock_script_boilerplate(namespace: str, entity_id: Optional[str] = None) -> list[str]:
    imports = sorted({name for names in BEDROCK_API_IMPORTS.values() for name in names})
    lines = [f'import {{ {", ".join(imports)} }} from "@minecraft/server";']
    if entity_id:
        lines += [
            '',
            f'// Bedrock Script API bootstrap for {namespace}:{entity_id}',
            f'const MOD_ID = "{namespace}:{sanitize_identifier(entity_id)}";',
            'function isTarget(entity) { return !!entity && (entity.typeId === MOD_ID || entity.typeId.endsWith(`:${MOD_ID.split(":").pop()}`)); }',
            '',
            'world.afterEvents.entitySpawn.subscribe(({ entity }) => {',
            '  if (!isTarget(entity)) return;',
            '  // attach per-entity tick / state here',
            '});',
            '',
            'world.afterEvents.entityHurt.subscribe(({ hurtEntity, damageSource }) => {',
            '  const entity = hurtEntity;',
            '  if (!isTarget(entity)) return;',
            '  // react to damage, status, or infection logic here',
            '});',
        ]
    return lines

def emit_bedrock_api_support_script(out_path: str, namespace: str, entity_id: str) -> None:
    lines = generate_bedrock_script_boilerplate(namespace, entity_id)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))







_LEGACY_RUN_PIPELINE = run_pipeline

JAVA_IMPORT_RE = re.compile(r'(?m)^\s*import\s+([\w.\*]+)\s*;')
JAVA_PACKAGE_RE = re.compile(r'(?m)^\s*package\s+([\w.]+)\s*;')
MIXIN_ANNOTATION_RE = re.compile(r'@Mixin\s*\((.*?)\)', re.DOTALL)
INJECT_ANNOTATION_RE = re.compile(r'@Inject\s*\((.*?)\)\s*(?:@[^\n]+\s*)*(?:public|protected|private|static|final|native|synchronized|abstract|\s)+[\w<>,\[\]]+\s+(\w+)\s*\(', re.DOTALL)
REDIRECT_ANNOTATION_RE = re.compile(r'@Redirect\s*\((.*?)\)\s*(?:@[^\n]+\s*)*(?:public|protected|private|static|final|native|synchronized|abstract|\s)+[\w<>,\[\]]+\s+(\w+)\s*\(', re.DOTALL)
OVERWRITE_ANNOTATION_RE = re.compile(r'@Overwrite\b(?:[^\n]*\n)+?(?:public|protected|private|static|final|native|synchronized|abstract|\s)+[\w<>,\[\]]+\s+(\w+)\s*\(', re.DOTALL)
ACCESSOR_ANNOTATION_RE = re.compile(r'@Accessor\b')
INVOKER_ANNOTATION_RE = re.compile(r'@Invoker\b')
FABRIC_ENTRYPOINT_RE = re.compile(r'implements\s+([^\{]+)')


def _strip_java_comments(source: str) -> str:
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    source = re.sub(r'(?m)//.*$', '', source)
    return source


def _safe_json_dump(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _ensure_main_import(main_path: str, import_line: str) -> None:
    os.makedirs(os.path.dirname(main_path), exist_ok=True)
    existing = ''
    if os.path.exists(main_path):
        with open(main_path, 'r', encoding='utf-8') as fh:
            existing = fh.read()
    if import_line.strip() not in existing:
        with open(main_path, 'w', encoding='utf-8') as fh:
            fh.write(import_line + ('\n' if not import_line.endswith('\n') else '') + existing)


def _extract_block(text: str, start_index: int) -> str:
    if start_index < 0 or start_index >= len(text):
        return ''
    brace = text.find('{', start_index)
    if brace == -1:
        return ''
    depth = 0
    for i in range(brace, len(text)):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[brace + 1:i]
    return text[brace + 1:]


def _read_text_file(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            return fh.read()
    except Exception:
        return ''


class JavaAST:
    def __init__(self, source: str):
        self._src = source or ''
        self._clean = _strip_java_comments(self._src)
        self._tree = None
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

    def _classes(self):
        self._parse()
        if self._tree is None:
            return []
        return [node for _, node in self._tree.filter(javalang.tree.TypeDeclaration)]

    def primary_class_name(self) -> Optional[str]:
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.TypeDeclaration):
                if hasattr(node, 'name'):
                    return node.name
        m = re.search(r'\bclass\s+(\w+)', self._clean)
        if m:
            return m.group(1)
        m = re.search(r'\binterface\s+(\w+)', self._clean)
        if m:
            return m.group(1)
        m = re.search(r'\benum\s+(\w+)', self._clean)
        if m:
            return m.group(1)
        return None

    def package_name(self) -> Optional[str]:
        m = JAVA_PACKAGE_RE.search(self._clean)
        return m.group(1) if m else None

    def imports(self) -> List[str]:
        return JAVA_IMPORT_RE.findall(self._clean)

    def annotation_value(self, annotation_name: str) -> Optional[str]:
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.Annotation):
                if getattr(node, 'name', None) == annotation_name:
                    elem = getattr(node, 'element', None)
                    if elem is None:
                        return None
                    if hasattr(elem, 'value'):
                        v = elem.value
                        return v.strip('"\'') if isinstance(v, str) else str(v)
                    return str(elem)
        m = re.search(rf'@{re.escape(annotation_name)}\s*\(\s*["\']([^"\']+)["\']\s*\)', self._clean)
        return m.group(1) if m else None

    def field_string_values(self, field_names: Set[str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.FieldDeclaration):
                for decl in getattr(node, 'declarators', []) or []:
                    if decl.name in field_names and getattr(decl, 'initializer', None) is not None:
                        init = decl.initializer
                        if isinstance(init, javalang.tree.Literal) and isinstance(init.value, str):
                            out[decl.name] = init.value.strip('"\'')
        if not out:
            for name in field_names:
                m = re.search(rf'\b{name}\b\s*=\s*["\']([^"\']+)["\']', self._clean)
                if m:
                    out[name] = m.group(1)
        return out

    def get_class_declarations(self) -> List:
        self._parse()
        if self._tree is None:
            return []
        return [node for _, node in self._tree.filter(javalang.tree.ClassDeclaration)]

    def superclass_name(self, cls_name: Optional[str] = None) -> Optional[str]:
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                if cls_name and node.name != cls_name:
                    continue
                if node.extends and hasattr(node.extends, 'name'):
                    return node.extends.name
        m = re.search(r'\bclass\s+' + (re.escape(cls_name) if cls_name else r'\w+') + r'\s+extends\s+(\w+)', self._clean)
        return m.group(1) if m else None

    def implemented_interfaces(self, cls_name: Optional[str] = None) -> List[str]:
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
                if cls_name and node.name != cls_name:
                    continue
                return [i.name for i in (node.implements or []) if hasattr(i, 'name')]
        m = re.search(r'\bclass\s+' + (re.escape(cls_name) if cls_name else r'\w+') + r'[^\{]*implements\s+([\w\s,<>.?]+)', self._clean)
        if not m:
            return []
        return [sanitize_identifier(x).split('.')[-1] for x in re.split(r',', m.group(1)) if x.strip()]

    def all_class_extends(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        for cls in self.get_class_declarations():
            if getattr(cls, 'extends', None) and hasattr(cls.extends, 'name'):
                out.append((cls.name, cls.extends.name))
        if out:
            return out
        for m in re.finditer(r'\bclass\s+(\w+)\s+extends\s+(\w+)', self._clean):
            out.append((m.group(1), m.group(2)))
        return out

    def method_names(self) -> Set[str]:
        names: Set[str] = set()
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.MethodDeclaration):
                names.add(node.name)
        if not names:
            for m in re.finditer(r'\b(?:public|protected|private|static|final|native|synchronized|abstract|\s)+[\w<>,\[\]]+\s+(\w+)\s*\(', self._clean):
                names.add(m.group(1))
        return names

    def method_body_source(self, method_name: str) -> Optional[str]:
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.MethodDeclaration):
                if node.name != method_name or not getattr(node, 'position', None):
                    continue
                lines = self._src.splitlines()
                start = max(0, node.position.line - 1)
                snippet = '\n'.join(lines[start:start + 500])
                brace = snippet.find('{')
                if brace == -1:
                    return snippet
                depth = 0
                for i in range(brace, len(snippet)):
                    if snippet[i] == '{':
                        depth += 1
                    elif snippet[i] == '}':
                        depth -= 1
                        if depth == 0:
                            return snippet[brace + 1:i]
                return snippet[brace + 1:]
        return _extract_method_body(self._src, method_name)

    def all_string_literals(self) -> List[str]:
        out: List[str] = []
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.Literal):
                if isinstance(node.value, str) and node.value.startswith('"'):
                    out.append(node.value.strip('"'))
        if not out:
            out.extend(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', self._clean))
        return out

    def object_creations_of(self, class_name: str) -> List:
        self._parse()
        if self._tree is None:
            return []
        return [node for _, node in self._tree.filter(javalang.tree.ClassCreator) if getattr(getattr(node, 'type', None), 'name', None) == class_name]

    def all_object_creation_types(self) -> List[str]:
        self._parse()
        if self._tree is None:
            return []
        out = []
        for _, node in self._tree.filter(javalang.tree.ClassCreator):
            if getattr(getattr(node, 'type', None), 'name', None):
                out.append(node.type.name)
        return out

    def invocations_of(self, method_name: str) -> List:
        self._parse()
        if self._tree is None:
            return []
        return [node for _, node in self._tree.filter(javalang.tree.MethodInvocation) if getattr(node, 'member', None) == method_name]

    def instanceof_types(self) -> Set[str]:
        out: Set[str] = set()
        self._parse()
        if self._tree is not None:
            for _, node in self._tree.filter(javalang.tree.BinaryOperation):
                if getattr(node, 'operator', None) == 'instanceof' and hasattr(node.operandr, 'name'):
                    out.add(node.operandr.name)
        if not out:
            for m in re.finditer(r'instanceof\s+(\w+)', self._clean):
                out.add(m.group(1))
        return out

    def class_extends(self, target_name: str, cls_name: Optional[str] = None) -> bool:
        return any(parent == target_name and (cls_name is None or child == cls_name) for child, parent in self.all_class_extends())

    @staticmethod
    def strip_generics(name: str) -> str:
        return re.sub(r'<.*?>', '', name or '').strip()

    @staticmethod
    def first_string_arg(invocation_node) -> Optional[str]:
        args = getattr(invocation_node, 'arguments', None) or []
        for arg in args:
            if isinstance(arg, javalang.tree.Literal) and isinstance(arg.value, str) and arg.value.startswith('"'):
                return arg.value.strip('"')
        return None


class JavaSymbolTable:
    JAVA_TYPE_TO_BEDROCK = {
        'Player': 'Player', 'ServerPlayer': 'Player', 'LocalPlayer': 'Player',
        'Entity': 'Entity', 'LivingEntity': 'Entity', 'Mob': 'Entity', 'Monster': 'Entity',
        'ItemStack': 'ItemStack', 'Item': 'ItemTypeStr', 'BlockPos': 'Vector3', 'Vec3': 'Vector3',
        'Vec3i': 'Vector3', 'Vector3f': 'Vector3', 'BlockState': 'BlockPermutation',
        'Level': 'Dimension', 'ServerLevel': 'Dimension', 'World': 'Dimension',
        'Container': 'Container', 'Inventory': 'Container', 'SimpleContainer': 'Container',
        'CompoundTag': 'DynamicProperties', 'CompoundNBT': 'DynamicProperties',
        'ListTag': 'DynamicArray', 'ResourceLocation': 'string',
        'int': 'number', 'float': 'number', 'double': 'number', 'long': 'number', 'short': 'number', 'byte': 'number',
        'boolean': 'boolean', 'String': 'string', 'void': 'void', 'Object': 'any',
    }

    TYPE_METHOD_MAP = {
        'Player': {
            'sendMessage': '{0}.sendMessage({1})', 'getHealth': '{0}.getComponent("minecraft:health").currentValue',
            'setHealth': '{0}.getComponent("minecraft:health").setCurrentValue({1})', 'getInventory': '{0}.getComponent("minecraft:inventory").container',
            'getPosition': '{0}.location', 'setPosition': '{0}.teleport({1})', 'addExperiencePoints': '{0}.addExperience({1})',
        },
        'Entity': {
            'getHealth': '{0}.getComponent("minecraft:health").currentValue', 'setHealth': '{0}.getComponent("minecraft:health").setCurrentValue({1})',
            'getPosition': '{0}.location', 'setPosition': '{0}.teleport({1})', 'getVelocity': '{0}.getVelocity()', 'setVelocity': '{0}.applyImpulse({1})',
            'kill': '{0}.kill()', 'remove': '{0}.remove()', 'addTag': '{0}.addTag({1})', 'removeTag': '{0}.removeTag({1})', 'hasTag': '{0}.hasTag({1})',
        },
        'ItemStack': {
            'getCount': '{0}.amount', 'setCount': '{0}.amount = {1}', 'grow': '{0}.amount += {1}', 'shrink': '{0}.amount -= {1}', 'isEmpty': '({0}.amount <= 0)',
        },
        'Dimension': {
            'setBlockState': '{0}.getBlock({1}).setPermutation({2})', 'getBlockState': '{0}.getBlock({1}).permutation', 'addParticle': '{0}.spawnParticle({1}, {2})',
            'playSound': '{0}.playSound({1}, {2})',
        },
        'DynamicProperties': {
            'getInt': '({0}.getDynamicProperty({1}) ?? 0)', 'putInt': '{0}.setDynamicProperty({1}, {2})',
            'getString': '({0}.getDynamicProperty({1}) ?? "")', 'putString': '{0}.setDynamicProperty({1}, {2})',
            'getBoolean': '({0}.getDynamicProperty({1}) ?? false)', 'putBoolean': '{0}.setDynamicProperty({1}, {2})',
        },
        'Vector3': {
            'add': '{{ x: {0}.x + {1}.x, y: {0}.y + {1}.y, z: {0}.z + {1}.z }}', 'subtract': '{{ x: {0}.x - {1}.x, y: {0}.y - {1}.y, z: {0}.z - {1}.z }}',
            'scale': '{{ x: {0}.x * {1}, y: {0}.y * {1}, z: {0}.z * {1} }}', 'length': 'Math.sqrt({0}.x**2 + {0}.y**2 + {0}.z**2)',
        },
    }

    _CAP_ENERGY = {'receiveEnergy', 'extractEnergy', 'getEnergyStored', 'getMaxEnergyStored', 'canReceive', 'canExtract'}
    _CAP_FLUID = {'fill', 'drain', 'getFluidAmount', 'getTankCapacity', 'getFluidInTank', 'getTanks', 'isFluidValid'}
    _CAP_ITEM = {'insertItem', 'extractItem', 'getStackInSlot', 'getSlots', 'isItemValid', 'getSlotLimit'}
    _CAP_ITEMSTACK = {'getCount', 'setCount', 'grow', 'shrink', 'isEmpty'}

    def __init__(self):
        self.classes: Dict[str, Dict] = {}
        self.variables: Dict[str, str] = {}
        self._qualifier_type_cache: Dict[str, str] = {}
        self.method_return_types: Dict[str, str] = {}
        self._method_to_capability: Dict[str, str] = {}

    def register_class(self, class_name: str, superclass: Optional[str] = None, interfaces: List[str] = None):
        self.classes.setdefault(class_name, {'superclass': superclass, 'interfaces': interfaces or [], 'methods': {}, 'fields': {}})

    def register_method(self, class_name: str, method_name: str, return_type: str, params: Dict[str, str]):
        self.register_class(class_name)
        self.classes[class_name]['methods'][method_name] = {'return': return_type, 'params': params}
        self.method_return_types[f'{class_name}.{method_name}'] = return_type

    def register_field(self, class_name: str, field_name: str, field_type: str):
        self.register_class(class_name)
        self.classes[class_name]['fields'][field_name] = field_type

    def set_variable_type(self, var_name: str, var_type: str):
        if not var_name:
            return
        self.variables[var_name] = var_type
        resolved = self._resolve_bedrock_type(var_type)
        if resolved:
            self._qualifier_type_cache[var_name] = resolved

    def get_variable_type(self, var_name: str) -> Optional[str]:
        return self.variables.get(var_name)

    def _resolve_bedrock_type(self, java_type: str) -> Optional[str]:
        base = re.sub(r'<.*?>', '', java_type or '').strip()
        return self.JAVA_TYPE_TO_BEDROCK.get(base)

    def get_bedrock_type_for_var(self, var_name: str) -> Optional[str]:
        if not var_name:
            return None
        if var_name in self._qualifier_type_cache:
            return self._qualifier_type_cache[var_name]
        if var_name in self.variables:
            return self._resolve_bedrock_type(self.variables[var_name])
        low = var_name.lower()
        if low in {'player', 'p', 'serverplayer', 'localplayer'}:
            return 'Player'
        if low in {'entity', 'mob', 'e', 'target', 'attacker', 'victim'}:
            return 'Entity'
        if low in {'stack', 'itemstack', 'item', 'helditem', 'mainhand', 'offhand'}:
            return 'ItemStack'
        if low in {'level', 'world', 'dimension', 'serverlevel', 'dim'}:
            return 'Dimension'
        if low in {'nbt', 'tag', 'compound', 'data', 'persistentdata'}:
            return 'DynamicProperties'
        if low in {'pos', 'blockpos', 'position', 'origin', 'loc', 'location'}:
            return 'Vector3'
        if low in {'inventory', 'container', 'inv', 'chest', 'slots'}:
            return 'Container'
        return None

    def resolve_method_call(self, qualifier: str, method: str, args: List[str]) -> Optional[str]:
        btype = self.get_bedrock_type_for_var(qualifier)
        if not btype:
            return None
        tmpl = self.TYPE_METHOD_MAP.get(btype, {}).get(method)
        if not tmpl:
            return None
        result = tmpl.replace('{0}', qualifier)
        for i, arg in enumerate(args):
            result = result.replace(f'{{{i + 1}}}', arg)
        return result

    def method_belongs_to_capability(self, method_name: str) -> Optional[str]:
        if method_name in self._CAP_ENERGY:
            return 'energy'
        if method_name in self._CAP_FLUID:
            return 'fluid'
        if method_name in self._CAP_ITEM:
            return 'item_handler'
        if method_name in self._CAP_ITEMSTACK:
            return 'itemstack'
        return None

    def _scan_regex(self, java_code: str):
        src = _strip_java_comments(java_code)
        for m in re.finditer(r'\bclass\s+(\w+)(?:\s+extends\s+(\w+))?', src):
            self.register_class(m.group(1), m.group(2))
        for m in re.finditer(r'(?m)^\s*(?:public|private|protected|static|final|volatile|transient|\s)+\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*(?:=|;)', src):
            self.set_variable_type(m.group(2), m.group(1))
        for m in re.finditer(r'\b(?:public|private|protected|static|final|synchronized|native|abstract|\s)+\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)', src):
            ret, name, params = m.groups()
            param_map = {}
            for p in [x.strip() for x in params.split(',') if x.strip()]:
                parts = p.split()
                if len(parts) >= 2:
                    param_map[parts[-1]] = parts[-2]
                    self.set_variable_type(parts[-1], parts[-2])
            if self.classes:
                cls = next(reversed(self.classes))
                self.register_method(cls, name, ret, param_map)

    def scan_java_file(self, java_code: str):
        if JAVALANG_AVAILABLE:
            try:
                tree = javalang.parse.parse(java_code)
                for _, node in tree.filter(javalang.tree.ClassDeclaration):
                    super_name = node.extends.name if node.extends and hasattr(node.extends, 'name') else None
                    interfaces = [i.name for i in (node.implements or []) if hasattr(i, 'name')]
                    self.register_class(node.name, super_name, interfaces)
                    for field in node.fields:
                        ftype = getattr(field.type, 'name', str(field.type))
                        for decl in field.declarators:
                            self.register_field(node.name, decl.name, ftype)
                            self.set_variable_type(decl.name, ftype)
                    for method in node.methods:
                        ret = getattr(method.return_type, 'name', 'void') if method.return_type else 'void'
                        params = {}
                        for p in method.parameters or []:
                            ptype = getattr(p.type, 'name', str(p.type))
                            params[p.name] = ptype
                            self.set_variable_type(p.name, ptype)
                        self.register_method(node.name, method.name, ret, params)
                for _, node in tree.filter(javalang.tree.LocalVariableDeclaration):
                    ltype = getattr(node.type, 'name', str(node.type))
                    for decl in node.declarators:
                        self.set_variable_type(decl.name, ltype)
                return
            except Exception:
                pass
        self._scan_regex(java_code)


def translate_expression(expr: object) -> Optional[str]:
    if expr is None:
        return None
    if isinstance(expr, str):
        return expr
    if JAVALANG_AVAILABLE:
        if isinstance(expr, javalang.tree.Literal):
            return str(expr.value)
        if isinstance(expr, javalang.tree.MemberReference):
            qualifier = f'{expr.qualifier}.' if getattr(expr, 'qualifier', None) else ''
            return f'{qualifier}{expr.member}'
        if isinstance(expr, javalang.tree.MethodInvocation):
            args = [translate_expression(a) for a in (expr.arguments or [])]
            args = [a for a in args if a is not None]
            qual = f'{expr.qualifier}.' if getattr(expr, 'qualifier', None) else ''
            return f'{qual}{expr.member}({", ".join(args)})'
        if isinstance(expr, javalang.tree.BinaryOperation):
            left = translate_expression(expr.operandl)
            right = translate_expression(expr.operandr)
            if left is not None and right is not None:
                return f'({left} {expr.operator} {right})'
        if isinstance(expr, javalang.tree.Cast):
            return translate_expression(expr.expression)
        if isinstance(expr, javalang.tree.TernaryExpression):
            cond = translate_expression(expr.condition)
            t = translate_expression(expr.if_true)
            f = translate_expression(expr.if_false)
            if cond and t and f:
                return f'({cond} ? {t} : {f})'
        if isinstance(expr, javalang.tree.This):
            return 'this'
        if isinstance(expr, javalang.tree.SuperMethodInvocation):
            args = [translate_expression(a) for a in (expr.arguments or []) if translate_expression(a) is not None]
            return f'super.{expr.member}({", ".join(args)})'
    if hasattr(expr, 'value'):
        return str(expr.value)
    return str(expr)


def translate_method_invocation(invocation: object, player: str, namespace: str, symbol_table: JavaSymbolTable) -> Optional[str]:
    member = getattr(invocation, 'member', '')
    qualifier = getattr(invocation, 'qualifier', None)
    if isinstance(qualifier, list):
        qualifier = qualifier[0] if qualifier else None
    args = getattr(invocation, 'arguments', []) or []
    arg_strs = [translate_expression(a) for a in args]
    arg_strs = [a for a in arg_strs if a is not None]
    if qualifier and isinstance(qualifier, str):
        resolved = symbol_table.resolve_method_call(qualifier, member, arg_strs)
        if resolved:
            return resolved
    if member in {'receiveEnergy', 'extractEnergy'} and arg_strs:
        return f'{member}({player}, {arg_strs[0]});'
    nbt_result = NBTTranslator.translate_nbt_call(member, args, namespace, player)
    if nbt_result:
        return nbt_result
    cap_type = symbol_table.method_belongs_to_capability(member)
    if cap_type == 'energy' and member == 'getEnergyStored':
        return f'getEnergyStored({player})'
    if cap_type == 'fluid' and member in {'fill', 'drain'}:
        return f'{member}({player}, {", ".join(arg_strs)})'
    bedrock_call = JavaToBedrockMethodMap.translate_method_call(member, args, qualifier)
    if bedrock_call:
        return bedrock_call
    return None


def translate_statement(stmt: object, player: str, namespace: str, symbol_table: Optional[JavaSymbolTable] = None) -> list:
    symbol_table = symbol_table or JavaSymbolTable()
    out: list[str] = []
    if JAVALANG_AVAILABLE and isinstance(stmt, javalang.tree.StatementExpression):
        expr = stmt.expression
        if isinstance(expr, javalang.tree.MethodInvocation):
            line = translate_method_invocation(expr, player, namespace, symbol_table)
            if line:
                return [f'    {line}' if not line.strip().endswith(';') else f'    {line}']
        if isinstance(expr, javalang.tree.Assignment):
            left = translate_expression(expr.expressionl)
            right = translate_expression(expr.value)
            if left and right:
                return [f'    {left} = {right};']
    if JAVALANG_AVAILABLE and isinstance(stmt, javalang.tree.LocalVariableDeclaration):
        for decl in stmt.declarators:
            init = translate_expression(decl.initializer) if decl.initializer else None
            out.append(f'    let {decl.name}' + (f' = {init}' if init else '') + ';')
        return out
    if JAVALANG_AVAILABLE and isinstance(stmt, javalang.tree.IfStatement):
        cond = translate_expression(stmt.condition)
        if cond:
            out.append(f'    if ({cond}) {{')
            body = stmt.then_statement
            stmts = body.statements if hasattr(body, 'statements') else ([body] if body else [])
            for s in stmts:
                out.extend(translate_statement(s, player, namespace, symbol_table))
            out.append('    }')
            if stmt.else_statement:
                out.append('    else {')
                body = stmt.else_statement
                stmts = body.statements if hasattr(body, 'statements') else ([body] if body else [])
                for s in stmts:
                    out.extend(translate_statement(s, player, namespace, symbol_table))
                out.append('    }')
            return out
    if JAVALANG_AVAILABLE and isinstance(stmt, javalang.tree.ReturnStatement):
        expr = translate_expression(stmt.expression) if stmt.expression else None
        return [f'    return {expr};' if expr else '    return;']
    if JAVALANG_AVAILABLE and isinstance(stmt, javalang.tree.ForStatement):
        out.append('    for (let i = 0; i < 1000; i++) {')
        body = stmt.body
        stmts = body.statements if hasattr(body, 'statements') else ([body] if body else [])
        for s in stmts:
            out.extend(translate_statement(s, player, namespace, symbol_table))
        out.append('    }')
        return out
    return out


def _extract_method_body(source: str, method_name: str) -> Optional[str]:
    if not source or not method_name:
        return None
    src = _strip_java_comments(source)
    if JAVALANG_AVAILABLE:
        try:
            tree = javalang.parse.parse(source)
            for _, node in tree.filter(javalang.tree.MethodDeclaration):
                if node.name != method_name:
                    continue
                pos = getattr(node, 'position', None)
                if pos:
                    lines = source.splitlines()
                    start = max(0, pos.line - 1)
                    snippet = '\n'.join(lines[start:start + 600])
                    brace = snippet.find('{')
                    if brace >= 0:
                        depth = 0
                        for i in range(brace, len(snippet)):
                            if snippet[i] == '{':
                                depth += 1
                            elif snippet[i] == '}':
                                depth -= 1
                                if depth == 0:
                                    return snippet[brace + 1:i]
        except Exception:
            pass
    pat = re.compile(rf'\b{re.escape(method_name)}\s*\([^)]*\)\s*\{{', re.DOTALL)
    m = pat.search(src)
    if not m:
        return None
    return _extract_block(src, m.start())


def _detect_project_loader() -> str:
    loaders = {'forge': 0, 'neoforge': 0, 'fabric': 0, 'quilt': 0}
    for root, _, files in os.walk('.'):
        for fname in files:
            low = fname.lower()
            path = os.path.join(root, fname)
            if low == 'fabric.mod.json':
                loaders['fabric'] += 3
                try:
                    data = json.loads(_read_text_file(path))
                    if isinstance(data, dict) and data.get('entrypoints'):
                        loaders['fabric'] += 1
                except Exception:
                    pass
            elif low == 'quilt.mod.json':
                loaders['quilt'] += 3
                try:
                    data = json.loads(_read_text_file(path))
                    if isinstance(data, dict) and data.get('quilt_loader'):
                        loaders['quilt'] += 1
                except Exception:
                    pass
            elif low == 'mods.toml':
                loaders['forge'] += 2
            elif low == 'neoforge.mods.toml':
                loaders['neoforge'] += 3
            elif low.endswith('.java'):
                code = _read_text_file(path)
                if '@Mixin' in code:
                    loaders['fabric'] += 1
                    loaders['quilt'] += 1
                if '@SubscribeEvent' in code:
                    loaders['forge'] += 1
    return max(loaders, key=loaders.get)


def _extract_mixin_target(code: str) -> Optional[str]:
    m = MIXIN_ANNOTATION_RE.search(code)
    if not m:
        return None
    body = m.group(1)
    quoted = re.findall(r'["\']([\w.$/]+)["\']', body)
    if quoted:
        return quoted[0].replace('/', '.')
    cls = re.search(r'\b([A-Za-z_][A-Za-z0-9_$.]+)\.class\b', body)
    return cls.group(1) if cls else None


def _mixin_event_guess(method_name: str, annotation_args: str, body: str) -> Optional[str]:
    needle = f'{method_name} {annotation_args} {body}'.lower()
    if any(k in needle for k in ('hurt', 'damage', 'attack')):
        return 'world.afterEvents.entityHurt'
    if any(k in needle for k in ('tick', 'update')):
        return 'system.runInterval'
    if any(k in needle for k in ('use', 'interact', 'rightclick', 'right_click')):
        return 'world.afterEvents.itemUse'
    if any(k in needle for k in ('place', 'break', 'destroy', 'remove')):
        return 'world.afterEvents.playerPlaceBlock'
    if any(k in needle for k in ('spawn', 'join')):
        return 'world.afterEvents.entitySpawn'
    return None


def _translate_mixin_body_to_js(body: str, namespace: str, safe_name: str) -> list[str]:
    if not body:
        return []
    lines = []
    if JAVALANG_AVAILABLE:
        try:
            dummy = f'public class Dummy {{ void d() {{ {body} }} }}'
            tree = javalang.parse.parse(dummy)
            for _, node in tree.filter(javalang.tree.MethodDeclaration):
                for stmt in node.body or []:
                    lines.extend(translate_statement(stmt, 'entity', namespace, JavaSymbolTable()))
            return lines
        except Exception:
            pass
    for ln in body.splitlines():
        ln = ln.rstrip()
        if ln:
            lines.append('    // ' + ln)
    return lines


def scan_mixins(java_files: Dict[str, str], namespace: str) -> list[str]:
    notes: list[str] = []
    out_dir = os.path.join(BP_FOLDER, 'scripts')
    os.makedirs(out_dir, exist_ok=True)
    for path, code in java_files.items():
        if '@Mixin' not in code and 'mixin' not in os.path.basename(path).lower():
            continue
        target = _extract_mixin_target(code)
        cls_name = JavaAST(code).primary_class_name() or os.path.splitext(os.path.basename(path))[0]
        safe_name = sanitize_identifier(cls_name)
        script_lines = [f'import {{ world, system }} from "@minecraft/server";', '']
        wrote = False
        if target:
            script_lines += [f'// Mixin target: {target}', f'// Source: {cls_name}', '']
        for ann_re, kind in ((INJECT_ANNOTATION_RE, 'inject'), (REDIRECT_ANNOTATION_RE, 'redirect'), (OVERWRITE_ANNOTATION_RE, 'overwrite')):
            for m in ann_re.finditer(code):
                annotation_args = m.group(1)
                method_name = m.group(2) if kind != 'overwrite' else m.group(1)
                method_body = _extract_method_body(code, method_name) or ''
                event = _mixin_event_guess(method_name, annotation_args, method_body)
                if event and event.startswith('system.runInterval'):
                    script_lines += [f'// {kind} {method_name} -> scheduled tick', 'system.runInterval(() => {']
                    script_lines += _translate_mixin_body_to_js(method_body, namespace, safe_name) or ['    // tick body could not be translated cleanly']
                    script_lines += ['}, 1);', '']
                elif event:
                    script_lines += [f'// {kind} {method_name} -> {event}', f'{event}.subscribe((event) => {{']
                    script_lines += _translate_mixin_body_to_js(method_body, namespace, safe_name) or ['    const entity = event.entity ?? event.player ?? event.hurtEntity ?? event.block ?? null;']
                    script_lines += ['});', '']
                else:
                    notes.append(f'[mixin] {cls_name}: {kind} {method_name} had no confident Bedrock mapping')
                wrote = True
        if ACCESSOR_ANNOTATION_RE.search(code) or INVOKER_ANNOTATION_RE.search(code):
            notes.append(f'[mixin] {cls_name}: accessor/invoker patterns need manual Bedrock porting or helper wrappers')
            wrote = True
        if wrote:
            out_path = os.path.join(out_dir, f'mixin_{safe_name}.js')
            with open(out_path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join(script_lines))
    return notes


def generate_bedrock_runtime_bridge(namespace: str) -> list[str]:
    return [
        'import { world, system, GameMode, ItemStack, BlockPermutation } from "@minecraft/server";',
        '',
        f'export const MOD_NAMESPACE = {json.dumps(namespace)};',
        'export const runtime = {',
        '  schedule: (fn, ticks = 1) => system.runInterval(fn, Math.max(1, ticks)),',
        '  onEntitySpawn: (fn) => world.afterEvents.entitySpawn.subscribe(fn),',
        '  onEntityHurt: (fn) => world.afterEvents.entityHurt.subscribe(fn),',
        '  onBlockPlace: (fn) => world.afterEvents.playerPlaceBlock.subscribe(fn),',
        '  onBlockBreak: (fn) => world.afterEvents.playerBreakBlock.subscribe(fn),',
        '  getProp: (entity, key, fallback = null) => entity?.getDynamicProperty?.(key) ?? fallback,',
        '  setProp: (entity, key, value) => entity?.setDynamicProperty?.(key, value),',
        '  hasTag: (entity, tag) => !!entity?.hasTag?.(tag),',
        '  tag: (entity, tag) => entity?.addTag?.(tag),',
        '  untag: (entity, tag) => entity?.removeTag?.(tag),',
        '  safeCall: (fn, fallback = undefined) => { try { return fn(); } catch { return fallback; } },',
        '};',
        '',
        'export function isTargetType(entity, id) {',
        '  return !!entity && typeof entity.typeId === "string" && (entity.typeId === id || entity.typeId.endsWith(`:${id.split(":").pop()}`));',
        '}',
        '',
        'export function withEntity(entity, fn) {',
        '  if (!entity) return;',
        '  try { fn(entity); } catch (e) { console.warn(`[runtime] ${e?.message ?? e}`); }',
        '}',
    ]


def _enhanced_postpass(namespace: str, java_files: Dict[str, str]) -> None:
    loader = _detect_project_loader()
    notes = []
    notes.append(f'[loader] detected project loader: {loader}')
    mixin_notes = scan_mixins(java_files, namespace)
    notes.extend(mixin_notes)
    scripts_dir = os.path.join(BP_FOLDER, 'scripts')
    os.makedirs(scripts_dir, exist_ok=True)
    runtime_path = os.path.join(scripts_dir, 'runtime_bridge.js')
    with open(runtime_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(generate_bedrock_runtime_bridge(namespace)))
    main_path = os.path.join(scripts_dir, 'main.js')
    _ensure_main_import(main_path, 'import "./runtime_bridge.js";\n')
    if os.path.exists(main_path):
        _ensure_main_import(main_path, 'import "./cap_registry.js";\n')
    report = {
        'namespace': namespace,
        'loader': loader,
        'java_files': len(java_files),
        'mixins': sum(1 for c in java_files.values() if '@Mixin' in c),
        'notes': notes[:500],
    }
    _safe_json_dump(os.path.join(OUTPUT_DIR, 'conversion_report.json'), report)
    if notes:
        port_notes = os.path.join(BP_FOLDER, 'PORTING_NOTES.txt')
        os.makedirs(os.path.dirname(port_notes), exist_ok=True)
        with open(port_notes, 'a', encoding='utf-8') as fh:
            fh.write('\n'.join(notes) + '\n')


def run_pipeline():
    _LEGACY_RUN_PIPELINE()
    try:
        java_files = read_all_java_files('.')
        namespace = detect_mod_id(java_files) if 'detect_mod_id' in globals() else None
        if not namespace:
            namespace = sanitize_identifier(os.path.basename(os.getcwd())) or 'converted'
        _enhanced_postpass(namespace, java_files)
    except Exception as e:
        try:
            log_critical_failure(f'Enhanced postpass failed: {e}')
        except Exception:
            pass







_MIXIN_PHASE_RE = re.compile(r'@At\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']', re.DOTALL)
_MIXIN_NAME_RE = re.compile(r'@(?:Inject|Redirect|Overwrite|Accessor|Invoker|ModifyVariable|ModifyArg|ModifyArgs|ModifyConstant|WrapOperation|WrapWithCondition)\b', re.DOTALL)

def _mixin_target_name(code: str) -> Optional[str]:
    m = MIXIN_ANNOTATION_RE.search(code)
    if not m:
        return None
    body = m.group(1)
    quoted = re.findall(r'["\']([\w.$/]+)["\']', body)
    if quoted:
        return quoted[0].replace('/', '.').split('.')[-1]
    cls = re.search(r'\b([A-Za-z_][A-Za-z0-9_$.]+)\.class\b', body)
    return cls.group(1).split('.')[-1] if cls else None

def _extract_mixin_target(code: str) -> Optional[str]:
    return _mixin_target_name(code)

def _mixin_annotation_names(ann_block: str) -> List[str]:
    return [m.group(1) for m in re.finditer(r'@(\w+)', ann_block or '')]

def _mixin_event_guess(target_cls: str, method_name: str, annotation_args: str, body: str, ann_names: Optional[List[str]] = None) -> Optional[str]:
    ann_names = ann_names or []
    needle = f'{target_cls} {method_name} {annotation_args} {body}'.lower()

    if any(k in needle for k in ('tick', 'update', 'inventorytick', 'aiset', 'servertick', 'clienttick')):
        return 'system.runInterval'
    if any(k in needle for k in ('chat', 'message', 'sendchat', 'chatsend')):
        return 'world.beforeEvents.chatSend'
    if any(k in needle for k in ('hurt', 'damage', 'attack', 'hurtentity')):
        return 'world.afterEvents.entityHurt'
    if any(k in needle for k in ('death', 'die', 'killed')):
        return 'world.afterEvents.entityDie'
    if any(k in needle for k in ('spawn', 'join', 'create', 'construct', 'addedtotick', 'entityjoin')):
        return 'world.afterEvents.entitySpawn'
    if any(k in needle for k in ('explode', 'explosion', 'detonate')):
        return 'world.afterEvents.explosion'
    if any(k in needle for k in ('pickup', 'pick up', 'pickupitem')):
        return 'world.afterEvents.entitySpawn'
    if any(k in needle for k in ('drop', 'toss', 'throw')):
        return 'world.afterEvents.entitySpawn'
    if any(k in needle for k in ('useon', 'place', 'blockactivated', 'interactblock', 'rightclickblock')):
        return 'world.afterEvents.playerPlaceBlock'
    if any(k in needle for k in ('break', 'destroy', 'mine', 'removeblock', 'leftclickblock')):
        return 'world.afterEvents.playerBreakBlock'
    if any(k in needle for k in ('interact', 'rightclick', 'use', 'attackentity', 'interactat', 'mount')):
        return 'world.afterEvents.playerInteractWithEntity'
    if any(k in needle for k in ('craft', 'crafted')):
        return 'world.afterEvents.itemCompleteUse'
    if any(k in needle for k in ('itemuse', 'useitem', 'finishusingitem', 'appendtooltip')):
        return 'world.afterEvents.itemUse'
    if any(k in needle for k in ('block', 'state', 'tileentity', 'worldgen')):
        return 'world.afterEvents.playerPlaceBlock'
    return None

def _infer_mixin_phase(annotation_args: str, body: str) -> str:
    text = f'{annotation_args} {body}'.lower()
    if any(k in text for k in ('cancellable = true', 'cancellable=true', '@at("head")', '@at(value = "head")', '@at("before")', '@at(value = "before")')):
        return 'before'
    if any(k in text for k in ('@at("tail")', '@at(value = "tail")', '@at("return")', '@at(value = "return")', '@at("end")', '@at(value = "end")')):
        return 'after'
    return 'after'

def _split_annotation_args(raw: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in _split_top_level(raw or ''):
        if '=' in part:
            k, v = part.split('=', 1)
            out[k.strip()] = v.strip()
    return out

def _extract_method_annotation_bundle(code: str, method_name: str) -> Tuple[List[str], str, str, str, List[Tuple[str, str]], Optional[str]]:
    ann, header, params_src, body = _extract_method_signature_block(code, method_name)
    if ann is None:
        return [], '', '', '', [], None
    annotations = _mixin_annotation_names(ann)
    params = _parse_java_params(params_src or '')
    ret_type = ''
    if header:
        hm = re.search(r'([\w<>,\[\].?$]+)\s+' + re.escape(method_name) + r'\s*\(', header)
        ret_type = hm.group(1) if hm else ''
    return annotations, ann or '', header or '', body or '', params, ret_type or None

def _event_subscription_lines(
    target_cls: str,
    method_name: str,
    body: str,
    wrapper: str,
    params: List[Tuple[str, str]],
    annotations: Dict[str, List[Tuple[List[str], Dict[str, str]]]],
) -> List[str]:
    chosen = []
    for key in ('Inject', 'Overwrite'):
        if annotations.get(key):
            chosen = annotations[key][0]
            break
    raw = ' '.join(list(chosen[0]) + [f'{k}={v}' for k, v in chosen[1].items()]) if chosen else ''
    at_name_m = re.search(r'@At\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']', raw, re.DOTALL)
    at_name = at_name_m.group(1) if at_name_m else ''
    event = _infer_target_event(target_cls, method_name, body, at_name, raw)
    if not event:
        return []

    lines = [f'// event bridge for {method_name} -> {event}']
    if event == 'system.runInterval':
        lines += [
            'system.runInterval(() => {',
            f'    {wrapper}();',
            '}, 1);',
            '',
        ]
        return lines

    lines.append(f'{event}.subscribe((event) => {{')
    for ptype, pname in params:
        if 'callbackinfo' in ptype.lower():
            continue
        lines.append(f'    const {pname} = {_param_binding_expr(ptype)};')
    call_args = ', '.join(pname for ptype, pname in params if 'callbackinfo' not in ptype.lower())
    lines.append(f'    {wrapper}({call_args});' if call_args else f'    {wrapper}(event);')
    lines.append('});')
    lines.append('')
    return lines

def _mixin_shadow_lines(cls_name: str, method_name: str, target_cls: str) -> List[str]:
    safe = sanitize_identifier(f'{cls_name}_{method_name}')
    return [
        f'// @Shadow {method_name} from {target_cls}',
        f'export const {safe} = {{ target: {json.dumps(target_cls)}, name: {json.dumps(method_name)} }};',
        '',
    ]

def _mixin_accessor_invoker_lines(
    kind: str,
    cls_name: str,
    method_name: str,
    return_type: str,
    params: List[Tuple[str, str]],
    annotations: Dict[str, List[Tuple[List[str], Dict[str, str]]]],
    target_cls: str,
    safe_name: str,
) -> List[str]:
    wrapper = f'{safe_name}__{method_name}'
    ann = annotations.get(kind, [([], {})])[0]
    named = ann[1]
    explicit = None
    for value in named.values():
        m = re.search(r'"([^"]+)"', value)
        if m:
            explicit = m.group(1)
            break
    if explicit is None and ann[0]:
        first = ann[0][0]
        m = re.search(r'"([^"]+)"', first)
        if m:
            explicit = m.group(1)
    explicit = explicit or method_name

    sig = ', '.join(p for _, p in params)
    if kind == 'Accessor':
        sig = sig or 'target'
        lines = [f'export function {wrapper}({sig}) {{']
        target_param = params[0][1] if params else 'target'
        if return_type.strip().lower() == 'void' or method_name.startswith('set'):
            field_name = explicit
            if method_name.startswith('set') and explicit == method_name:
                field_name = method_name[3:4].lower() + method_name[4:]
            value_name = params[-1][1] if len(params) > 1 else 'value'
            lines += [
                f'    const target = {target_param};',
                '    if (!target) return;',
                f'    target[{json.dumps(field_name)}] = {value_name};',
                '    return;',
            ]
        else:
            field_name = explicit
            lines += [
                f'    const target = {target_param};',
                f'    return target ? target[{json.dumps(field_name)}] : undefined;',
            ]
        lines += ['}', '']
        return lines

    sig = sig or 'target'
    lines = [f'export function {wrapper}({sig}) {{']
    target_param = params[0][1] if params else 'target'
    call_args = ', '.join(p for _, p in params[1:])
    lines += [
        f'    const target = {target_param};',
        f'    if (!target || typeof target[{json.dumps(explicit)}] !== "function") return undefined;',
        f'    return target[{json.dumps(explicit)}]({call_args});' if call_args else f'    return target[{json.dumps(explicit)}]();',
        '}',
        '',
    ]
    return lines

def _mixin_wrapper_lines(
    cls_name: str,
    method_name: str,
    return_type: str,
    params: List[Tuple[str, str]],
    body: str,
    namespace: str,
    safe_name: str,
    annotations: Dict[str, List[Tuple[List[str], Dict[str, str]]]],
    target_cls: str,
) -> List[str]:
    wrapper = f'{safe_name}__{method_name}'
    callback_params = [p for p in params if 'callbackinfo' in p[0].lower()]
    non_callback_params = [p for p in params if 'callbackinfo' not in p[0].lower()]
    signature = ', '.join(p for _, p in non_callback_params)
    lines: List[str] = [f'export function {wrapper}({signature}) {{']

    if callback_params:
        lines.append('    let __mixin_cancelled = false;')
        for ptype, pname in callback_params:
            if 'callbackinforeturnable' in ptype.lower():
                lines += [
                    f'    let __{pname}_returnValue = undefined;',
                    f'    const {pname} = {{',
                    '        cancel: () => { __mixin_cancelled = true; },',
                    f'        setReturnValue: (v) => {{ __mixin_cancelled = true; __{pname}_returnValue = v; }},',
                    f'        getReturnValue: () => __{pname}_returnValue,',
                    '        isCancelled: () => __mixin_cancelled,',
                    '    };',
                ]
            else:
                lines += [
                    f'    const {pname} = {{',
                    '        cancel: () => { __mixin_cancelled = true; },',
                    '        isCancelled: () => __mixin_cancelled,',
                    '    };',
                ]

    local_body = _translate_java_body_to_js(body, namespace, safe_name)
    if not local_body:
        local_body = ['    // no translated body']
    lines.extend(local_body)

    if callback_params:
        lines.append('    if (__mixin_cancelled) return;')
    lines.append('}')
    lines.append('')
    return lines

def _mixin_modifier_lines(
    kind: str,
    cls_name: str,
    method_name: str,
    params: List[Tuple[str, str]],
    body: str,
    namespace: str,
    safe_name: str,
    annotations: Dict[str, List[Tuple[List[str], Dict[str, str]]]],
    target_cls: str,
) -> List[str]:
    wrapper = f'{safe_name}__{method_name}'
    sig = ', '.join(p for _, p in params) or 'value'
    lines: List[str] = [f'export function {wrapper}({sig}) {{']
    local_body = _translate_java_body_to_js(body, namespace, safe_name)
    if kind == 'ModifyConstant':
        original_name = params[0][1] if params else 'original'
        lines.append(f'    const original = {original_name};')
        lines.extend(local_body or ['    return original;'])
        if not any('return' in line for line in local_body):
            lines.append('    return original;')
    elif kind == 'ModifyVariable':
        var_name = params[0][1] if params else 'value'
        lines.append(f'    let value = {var_name};')
        lines.extend(local_body or ['    return value;'])
        if not any('return' in line for line in local_body):
            lines.append('    return value;')
    elif kind in ('ModifyArg', 'ModifyArgs'):
        lines.append('    const args = Array.from(arguments);')
        lines.extend(local_body or ['    return args;'])
        if not any('return' in line for line in local_body):
            lines.append('    return args;')
    elif kind == 'WrapOperation':
        lines.append('    const operation = arguments[0];')
        lines.append('    const args = Array.from(arguments).slice(1);')
        lines.extend(local_body or ['    return operation(...args);'])
        if not any('return' in line for line in local_body):
            lines.append('    return operation(...args);')
    elif kind == 'WrapWithCondition':
        lines.append('    const condition = arguments[0];')
        lines.append('    const operation = arguments[1];')
        lines.append('    const args = Array.from(arguments).slice(2);')
        lines.extend(local_body or ['    return condition ? operation(...args) : undefined;'])
        if not any('return' in line for line in local_body):
            lines.append('    return condition ? operation(...args) : undefined;')
    else:
        lines.extend(local_body or ['    // unsupported modifier body'])
    lines.append('}')
    lines.append('')
    return lines

def scan_mixins(java_files: Dict[str, str], namespace: str) -> List[str]:
    notes: List[str] = []
    out_dir = os.path.join(BP_FOLDER, 'scripts')
    os.makedirs(out_dir, exist_ok=True)

    for path, code in java_files.items():
        if '@Mixin' not in code and 'mixin' not in os.path.basename(path).lower():
            continue

        cls_name = JavaAST(code).primary_class_name() or os.path.splitext(os.path.basename(path))[0]
        safe_name = sanitize_identifier(cls_name)
        target_cls = _mixin_target_name(code) or extract_class_name(code) or cls_name

        script_lines: List[str] = [f'import {{ world, system }} from "@minecraft/server";', '']
        wrote_anything = False


        for sm in re.finditer(r'@Shadow\b[^\n]*\s+(?:public|protected|private|static|final|\s)+[\w<>,\[\].?$]+\s+(\w+)\s*(?:=|;)', code):
            script_lines.extend(_mixin_shadow_lines(cls_name, sm.group(1), target_cls))
            wrote_anything = True

        for m in _MIXIN_METHOD_RE.finditer(code):
            ann_block = m.group('ann') or ''
            method_name = m.group('name')
            return_type = m.group('rtype') or 'void'
            params = _parse_java_params(m.group('params') or '')
            body = _extract_block(code, m.start('head')) or ''
            annotations = _annotation_text_map(ann_block)
            ann_names = _mixin_annotation_names(ann_block)

            if not ann_names:
                continue

            has_accessor = 'Accessor' in ann_names
            has_invoker = 'Invoker' in ann_names
            has_shadow = 'Shadow' in ann_names
            has_inject = 'Inject' in ann_names
            has_overwrite = 'Overwrite' in ann_names
            has_redirect = 'Redirect' in ann_names
            has_modify = any(k in ann_names for k in ('ModifyVariable', 'ModifyArg', 'ModifyArgs', 'ModifyConstant', 'WrapOperation', 'WrapWithCondition'))

            if has_shadow and not (has_accessor or has_invoker):
                script_lines.extend(_mixin_shadow_lines(cls_name, method_name, target_cls))
                wrote_anything = True
                continue

            if has_accessor:
                script_lines.extend(_mixin_accessor_invoker_lines('Accessor', cls_name, method_name, return_type, params, annotations, target_cls, safe_name))
                notes.append(f'[mixin] {cls_name}: accessor {method_name} converted into helper wrapper')
                wrote_anything = True
                continue

            if has_invoker:
                script_lines.extend(_mixin_accessor_invoker_lines('Invoker', cls_name, method_name, return_type, params, annotations, target_cls, safe_name))
                notes.append(f'[mixin] {cls_name}: invoker {method_name} converted into helper wrapper')
                wrote_anything = True
                continue

            if has_modify:
                kind = next(k for k in ('ModifyVariable', 'ModifyArg', 'ModifyArgs', 'ModifyConstant', 'WrapOperation', 'WrapWithCondition') if k in ann_names)
                script_lines.extend(_mixin_modifier_lines(kind, cls_name, method_name, params, body, namespace, safe_name, annotations, target_cls))
                wrote_anything = True

                event = _mixin_event_guess(target_cls, method_name, ann_block, body, ann_names)
                if event:
                    script_lines.extend(_event_subscription_lines(target_cls, method_name, body, f'{safe_name}__{method_name}', params, annotations))
                else:
                    notes.append(f'[mixin] {cls_name}: {kind} {method_name} exported as helper wrapper')
                continue

            if has_inject or has_overwrite or has_redirect:
                script_lines.extend(_mixin_wrapper_lines(cls_name, method_name, return_type, params, body, namespace, safe_name, annotations, target_cls))
                wrote_anything = True
                event = _mixin_event_guess(target_cls, method_name, ann_block, body, ann_names)
                if event:
                    script_lines.extend(_event_subscription_lines(target_cls, method_name, body, f'{safe_name}__{method_name}', params, annotations))
                else:
                    if has_redirect:
                        notes.append(f'[mixin] {cls_name}: redirect {method_name} converted to wrapper helper; call-site redirection is not exact on Bedrock')
                    else:
                        notes.append(f'[mixin] {cls_name}: {method_name} translated as helper wrapper only (no Bedrock event mapping)')
                continue


            if re.search(r'\b(public|protected|private)\b', m.group('head') or ''):
                script_lines.extend(_mixin_wrapper_lines(cls_name, method_name, return_type, params, body, namespace, safe_name, annotations, target_cls))
                wrote_anything = True
                notes.append(f'[mixin] {cls_name}: exported helper {method_name}')

        if wrote_anything:

            script_lines = generate_bedrock_script_boilerplate(namespace, target_cls) + [''] + script_lines
            out_path = os.path.join(out_dir, f'mixin_{safe_name}.js')
            with open(out_path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join(script_lines))
            print(f'[mixin] Wrote {out_path}')

    return notes

def scan_fabric_quilt_mixins(java_files: Dict[str, str], namespace: str) -> List[str]:
    return scan_mixins(java_files, namespace)

if __name__ == "__main__":
    main()