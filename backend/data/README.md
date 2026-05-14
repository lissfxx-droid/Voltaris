# backend/data/

存放 jlcparts 元件库 SQLite 数据库。**不进 git**（见 `pcb-system/.gitignore`）。

## cache.sqlite3

完整嘉立创元件库快照，~80k 元件 (~27GB 解压后)。来自社区项目 [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts)，每天 3 次同步 JLCPCB OpenAPI。

### 下载

```bash
cd backend/data

# 下载 41 个分卷（cache.zip + cache.z01 ~ cache.z40，约 2GB）
curl -fsSL -o cache.zip https://yaqwsx.github.io/jlcparts/data/cache.zip
for i in $(seq -f "%02g" 1 40); do
  curl -fsSL -o "cache.z$i" "https://yaqwsx.github.io/jlcparts/data/cache.z$i"
done

# 解压（需要 7z，因为 zip 标准库不支持多卷）
# Ubuntu/Debian: sudo apt install p7zip-full
# macOS: brew install p7zip
7z x cache.zip

# 验证
ls -lh cache.sqlite3   # ~27GB
sqlite3 cache.sqlite3 "SELECT COUNT(*) FROM components"
```

### 必加的索引（jlcparts 默认没建，少了查询会全表扫描）

下载完 cache.sqlite3 后**必须**建这几个索引，否则 `lcsc_lookup.py` 的 mpn / passive 查询会卡几分钟：

```bash
sqlite3 cache.sqlite3 <<'EOF'
CREATE INDEX IF NOT EXISTS components_mfr      ON components(mfr);
CREATE INDEX IF NOT EXISTS components_cat_pkg  ON components(category_id, package);
CREATE INDEX IF NOT EXISTS components_cat_basic ON components(category_id, basic, stock);
EOF
```

每条索引 1-3 分钟（27GB 库），命令行不返回是正常的，**不要 Ctrl+C**。

加完后：
- `lcsc_lookup.py mpn STM32G431CBT6` 秒回
- `lcsc_lookup.py passive Resistor 10k 0603 --basic` 秒回
- `lcsc_lookup.py detail C529355` 本来就秒回（主键索引）

### 表结构

```sql
components(
  lcsc INTEGER PRIMARY KEY,    -- C编号去掉 C 前缀的数字 (C529355 → 529355)
  category_id INTEGER,         -- → categories.id
  mfr TEXT,                    -- 制造商型号 (MPN)
  package TEXT,                -- 封装 (0603 / LQFP48 / ...)
  joints INTEGER,              -- 引脚数
  manufacturer_id INTEGER,     -- → manufacturers.id
  basic INTEGER,               -- 0/1 基础库 (SMT 不收 setup fee)
  preferred INTEGER,           -- 0/1 优选库
  description TEXT,
  datasheet TEXT,
  stock INTEGER,
  price TEXT,                  -- JSON 阶梯价
  extra TEXT,                  -- JSON 参数化数据 (resistance/voltage/...)
  jlc_extra TEXT               -- JSON JLCPCB 专属字段
)

manufacturers(id, ...)
categories(id, ...)
jlcpcb_component_details(...)
```

### 刷新策略

- **数据时效**：jlcparts 每天 3 次同步，本地 cache 视使用频率每月或每季手动 re-pull 一次
- **如何刷新**：删掉旧文件，重跑上面的下载命令

### 备选数据源

如果 yaqwsx/jlcparts 项目停摆：
- **CDFER/jlcpcb-parts-database** — 仅库存元件，~1GB
- **tscircuit/jlcsearch** — 优化版 ~2GB
- **LCSC OpenAPI** — 官方但要申请 accessKey + secretKey
