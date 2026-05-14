# CircuitIR 规范 v1.0

电路原理图的**确定性目标格式**（compile target）。

---

## 1. 这是什么

一份合规的 CircuitIR 文件 = 一个**已经设计完毕、不含任何不确定性**的电路定义。脚本读取它，直接生成 EDA 工程文件（`.epru` / `.kicad_sch` / ...）。

```
设计阶段 (AI / 人类) ──产出──> CircuitIR ──脚本──> .epru
                                  ↑
                          所有不确定性已消除
```

> ⚠ **CircuitIR 不是 IR（Intermediate Representation），而是 OR（Output Representation）**。任何含义为"也许 / 估计 / 待验证"的字段都禁止出现。

---

## 2. 强制约束

### 2.1 禁止的字段

下列字段在任何位置都不允许出现：

| 字段 | 为什么禁止 |
|------|-----------|
| `notes`, `assumptions`, `warnings`, `todos`, `confidence` | 这些表达不确定性，与"已敲定"矛盾 |
| `defaults` | 默认值是 hedging；脚本不允许"如果没写就用 100nF" |
| `role` (在 parts 上) | 语义提示，脚本不消费 |
| `topology` (在 modules 上) | 同上 |
| `description` 含 "auto-extracted / review / verify" 等动词 | 是 disclaimer，不是描述 |

### 2.2 强制的字段

| 字段 | 要求 |
|------|------|
| `schema_version` | 必需，固定 `"1.0"` |
| `project.name` | 必需，工程名 |
| `parts.<REF>` | 必需，每个元件 |
| `parts.<REF>.lcsc` 或 `parts.<REF>.mpn` | **二选一必填** — 脚本靠这个去元件库找 symbol/footprint |
| `nets.<NAME>` | 必需，每条网络的所有 pin 必须**完整列出**（GND 不允许省略） |
| pin 引用 `<REF>.<PIN>` | 必需可解析 — 元件库里能找到该 pin |

### 2.3 闭合性规则

| 规则 | 说明 |
|------|------|
| 每个 `nets` 中引用的 `<REF>` 必须存在于 `parts` | 否则生成失败 |
| 每个 pin 在所有 nets 中**有且只能**出现 1 次 | 同一引脚不能属于多个网络 |
| `modules.<id>.parts` 中的每个 ref 必须存在于 `parts` | 同上 |
| `buses.<id>.signals` 中引用的 net 名必须存在于 `nets` | 同上 |

校验失败 = 文件无效 = 脚本拒绝处理。**没有"警告"级别**。

---

## 3. Schema

```yaml
schema_version: "1.0"        # 必需，字符串

project:                     # 必需
  name: string               # 必需，工程名（无空格，A-Za-z0-9_-）
  revision: string           # 可选

parts:                       # 必需
  <REF>:                     # ref 是 key (R1, U7, CN2 ...)
    lcsc: string             # 与 mpn 二选一必填
    mpn: string              # 与 lcsc 二选一必填
    value: string            # 可选，显示在原理图标签上
    designator: string       # 可选，默认 = key

nets:                        # 必需
  <NET_NAME>:                # 网络名 (PWR_12V, GND, CAN_H ...)
    - <REF>.<PIN>            # 引脚引用，至少 2 个 endpoint
    - ...

modules:                     # 可选 — 仅用于原理图分页/分块
  <MODULE_ID>:
    parts: [<REF>, ...]      # 该模块包含的元件 ref

buses:                       # 可选 — 仅用于自动添加 bus label
  <BUS_ID>:
    type: string             # i2c | spi | uart | can | usb | swd
    signals:                 # role → net_name
      <ROLE>: <NET_NAME>
```

**只有这五个顶级键**：`schema_version`, `project`, `parts`, `nets`, `modules`, `buses`。其他键禁止。

---

## 4. 字段细则

### 4.1 `parts.<REF>`

```yaml
R1:    { lcsc: C2906982, value: 10kΩ }
U7:    { lcsc: C529355,  value: STM32G431CBT6 }
C1:    { lcsc: C1648,    value: 20pF }
```

- `lcsc`：嘉立创立创编号（`C` 开头）— 优先字段，决定 symbol/footprint/3D 模型
- `mpn`：制造商料号 — 当 lcsc 缺失时使用
- `value`：原理图标签显示值（电阻阻值、电容容值、IC 型号）；不参与电气逻辑
- `designator`：默认 = key（如 `R1`）；只有当显示位号与 key 不同时才需要

### 4.2 `nets.<NAME>`

每条网络是一个**完整的引脚列表**。同一网络内所有 pin 电气等同。

```yaml
GND:
  - CN2.2          # 必须列出每一个接地脚
  - U7.VSS
  - C1.1
  - C2.2
  - ...            # 不允许任何省略

PWR_12V:
  - CN2.1
  - U4.IN
  - C12.1
  - R20.2
```

#### 引脚引用语法

格式：`<REF>.<PIN>`，其中 `<PIN>` 是元件库里**确定**的引脚标识：

| 元件类型 | PIN 取值 | 示例 |
|---------|---------|------|
| IC | 元件库定义的引脚名 | `U7.PA13`, `U7.VDD`, `U5.CANH` |
| 被动二脚件 | 编号 | `R1.1`, `C5.2`, `L1.1` |
| 极性件 | 极性符号 | `D1.A` / `D1.K`, `Q1.G` / `Q1.D` / `Q1.S` |
| 连接器 | 编号 | `CN1.1`, `CN1.2` |

### 4.3 `modules.<MODULE_ID>` (可选)

```yaml
modules:
  power:  { parts: [U4, U3, L1, C12, C13, C14, C15, C16, C17] }
  mcu:    { parts: [U7, X1, C1, C2, R1, C3, RESET, R13, CN3] }
  motor:  { parts: [U2, R4, R5, R10, ..., U1] }
  can:    { parts: [U5, D1, R15, R14, R16, CN2] }
```

- 如果存在：每个 `parts` 中的 ref **应**出现在恰好一个 module（共享件可以例外）
- 用途：脚本生成多 sheet 原理图时按 module 分页
- **不存在不影响生成** — 脚本会把全部元件画在一页

### 4.4 `buses.<BUS_ID>` (可选)

```yaml
buses:
  CAN1:
    type: can
    signals: { h: CAN_H, l: CAN_L, tx: CAN_TX, rx: CAN_RX }
  SWD:
    type: swd
    signals: { swdio: SWDIO, swclk: SWCLK, nrst: NRST }
```

- 用途：脚本在原理图上加 bus 标签 / 总线打包
- 所有 signals 引用的 net 必须存在
- **不影响电气连接** — 电气连接由 `nets` 决定

---

## 5. 校验

校验器在脚本读取前必须运行。**所有失败均为 error，不存在 warning**：

```python
def validate(ir):
    assert ir["schema_version"] == "1.0"
    assert "name" in ir["project"]
    # 元件必须有 lcsc 或 mpn
    for ref, p in ir["parts"].items():
        assert "lcsc" in p or "mpn" in p, f"{ref}: missing lcsc/mpn"
    # net 引用闭合
    seen_pins = set()
    for net, pins in ir["nets"].items():
        for pinref in pins:
            ref, pin = pinref.split(".", 1)
            assert ref in ir["parts"], f"net {net}: unknown ref {ref}"
            assert pinref not in seen_pins, f"pin {pinref} appears in multiple nets"
            seen_pins.add(pinref)
    # module/bus 引用闭合
    for mid, m in ir.get("modules", {}).items():
        for ref in m["parts"]:
            assert ref in ir["parts"], f"module {mid}: unknown ref {ref}"
    for bid, b in ir.get("buses", {}).items():
        for role, net in b["signals"].items():
            assert net in ir["nets"], f"bus {bid}: unknown net {net}"
```

---

## 6. 完整示例

见 `example.thinir.yaml`。

---

## 附录 A：与设计阶段格式的关系

设计阶段（AI 创作 / 探索）可能用任何带 `assumptions / confidence / role` 等元字段的"厚 IR"格式。**但向 CircuitIR 转换时必须丢弃所有此类字段**：

```
设计阶段 IR (含不确定性)  ──消除假设──> CircuitIR (确定性)  ──脚本──> .epru
   ↑                                       ↑
   AI 工作面                         脚本输入面
```

如果转换时存在无法消除的假设（如"R15 是否填装"未定），转换必须**失败**而不是输出带 `assumptions:` 的 CircuitIR。
