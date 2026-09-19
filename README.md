# GS1 条码元素串 / Digital Link 解析 API

基于 Python + FastAPI 的 GS1 解析服务。`/parse` 接口同时接受两种输入：

1. **元素串（Element String）**：扫码枪原始输出（含 ASCII 29 / FNC1 分隔符）；
2. **GS1 Digital Link URI**：以 `http://` 或 `https://` 开头的链接，AI/值对位于路径
   （`/AI/值/AI/值`）和查询参数（`?AI=值&AI=值`）中。

两种输入都返回保持原顺序的结构化元素，并完成同一套字符集、长度、GTIN Mod-10
校验位与真实日期校验。

## 一键启动

```bash
docker compose up --build
```

启动后访问：

- API 地址：http://localhost:8080
- 交互式文档（Swagger UI）：http://localhost:8080/docs
- 健康检查：http://localhost:8080/health

## 支持的 AI

| AI   | 含义        | 长度            | 字符集                          |
| ---- | ----------- | --------------- | ------------------------------- |
| 01   | GTIN        | 固定 14 位数字  | 0-9，含 Mod-10 校验位验证       |
| 17   | 效期 YYMMDD | 固定 6 位数字   | 0-9，校验真实日期（含闰年）     |
| 10   | 批号        | 可变 1-20 字符  | GS1 AI 字符集 82                |
| 21   | 序列号      | 可变 1-20 字符  | GS1 AI 字符集 82                |
| 310n | 净重（千克）| 固定 6 位数字   | 0-9，n=0～9 为隐含小数位数      |
| 320n | 净重（磅）  | 固定 6 位数字   | 0-9，n=0～9 为隐含小数位数      |

`310n` / `320n` 是四位应用标识符：第四位 `n` 给出值的隐含小数位数（0～9），
其后紧跟固定 6 位数字。例如 `3102001234` 中 AI 为 `3102`、原始值 `value` 为
`001234`，实际重量 = 1234 ÷ 10² = **12.34 kg**；`3201029000` 为 **2900.0 lb**。
响应中这两个族的元素除保留原始 `value` 外，还会返回数值型 `decimal_value`
与字符串 `unit`（`kg` 或 `lb`）；其余 AI 不包含这两个字段。

解析规则：

- AI 按**最长可匹配**识别：先尝试匹配四位标识符（310n/320n 族），不命中再回退到
  两位 AI（01/10/17/21），因此四位标识符与两位 AI 无需分隔符即可邻接。
- 固定长度字段（01、17、310n、320n）按长度自动定界，无需分隔符。
- 可变长度字段（10、21）除位于串末尾外，必须以分隔符 ASCII 29（GS，扫码枪 FNC1）
  结束；JSON 中以 `\u001d` 表示。
- AI 17 的日字段为 `00` 时按 GS1 规范表示当月最后一天；年份按 20YY 解释。
- 仅出现 `310` / `320` 三位前缀而缺少第 4 位精度位（输入结束、遇分隔符或为
  非数字字符）时返回 `422 INVALID_PRECISION`；6 位值位数不足返回
  `FIELD_TOO_SHORT`，值中含非数字字符返回 `INVALID_CHARACTER`。
- `data` 以 `http://` 或 `https://` 开头时按 GS1 Digital Link URI 解析，否则按
  元素串解析，两种输入行为一致。

### Digital Link URI 规则

- 路径段必须成对出现：`/AI/值/AI/值...`；查询参数按 `AI=值&AI=值` 解析（参数没有
  等号时值为空，会触发 `FIELD_EMPTY`）。
- 值先做百分号 UTF-8 解码（`%XX`），再执行与元素串完全相同的字符集、长度、校验位与
  日期校验；`offset` 始终指向**原始 URI** 中的字节位置（解码后字符报错时定位到它的
  首个编码字节，即 `%` 所在字节）。
- 未知 AI、路径内重复 AI、查询参数内重复 AI，以及同一 AI 同时出现在路径和查询参数
  中，均返回 `422`。
- 响应中路径提取到的元素按路径顺序在前，查询参数提取到的元素按参数顺序在后。
- 片段（`#...`）不属于 Digital Link 数据，解析时忽略。

## 使用示例

### 元素串

请求（注意批号与序列号之间的 `\u001d` 分隔符）：

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"data": "01095011015300031725013110ABC123\u001d21SN0001"}'
```

响应 `200 OK`，元素按原始顺序返回，`offset` 为 AI 在输入中的字节偏移：

```json
{
  "elements": [
    { "ai": "01", "name": "GTIN",     "value": "09501101530003", "offset": 0  },
    { "ai": "17", "name": "EXPIRY",   "value": "250131",         "offset": 16 },
    { "ai": "10", "name": "BATCH/LOT","value": "ABC123",         "offset": 24 },
    { "ai": "21", "name": "SERIAL",   "value": "SN0001",         "offset": 33 }
  ]
}
```

重量 AI（310n/320n）的响应额外携带 `decimal_value` 与 `unit`，且固定长度字段
无需分隔符即可与其他 AI 邻接：

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"data": "01095011015300033102001234"}'
```

```json
{
  "elements": [
    { "ai": "01",   "name": "GTIN",           "value": "09501101530003", "offset": 0 },
    { "ai": "3102", "name": "NET WEIGHT (kg)","value": "001234", "offset": 16,
      "decimal_value": 12.34, "unit": "kg" }
  ]
}
```

`decimal_value` 是把原始 6 位数字除以 10ⁿ 得到的 JSON 数值（n=0 时例如
`23000.0`），`value` 始终保留原始 6 位字符串。

### GS1 Digital Link URI

路径和查询参数混用的请求（路径中的元素在前，查询参数中的元素在后）：

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"data": "https://id.gs1.org/01/09501101530003/17/250131?10=ABC123&21=SN0001"}'
```

响应与元素串完全一致，`offset` 是 AI 在**原 URI** 中的字节偏移：

```json
{
  "elements": [
    { "ai": "01", "name": "GTIN",      "value": "09501101530003", "offset": 19 },
    { "ai": "17", "name": "EXPIRY",    "value": "250131",         "offset": 37 },
    { "ai": "10", "name": "BATCH/LOT", "value": "ABC123",         "offset": 47 },
    { "ai": "21", "name": "SERIAL",    "value": "SN0001",         "offset": 57 }
  ]
}
```

值可使用百分号编码，按 UTF-8 解码后再做同一套校验。下面的批号解码后为
`Lot A/100`（百分号编码指向原 URI 字节位置，示例中 `/` 编码为 `%2F`；
注意空格不属于字符集 82，仅作编码演示）：

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"data": "https://id.gs1.org/10/Lot%20A%2F100"}'
```

该请求会返回 `422 INVALID_CHARACTER`，`offset` 指向编码空格的 `%20` 首字节。
仅含合法字符的示例：

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"data": "https://id.gs1.org/10/Lot%2FA%2F100"}'
```

解码后批号为 `Lot/A/100`，返回 `200`。

重量 AI 在 Digital Link 中的行为与元素串完全一致（路径或查询参数均可）：

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"data": "https://id.gs1.org/01/09501101530003/3201/029000"}'
```

```json
{
  "elements": [
    { "ai": "01",   "name": "GTIN",            "value": "09501101530003", "offset": 19 },
    { "ai": "3201", "name": "NET WEIGHT (lb)", "value": "029000", "offset": 37,
      "decimal_value": 2900.0, "unit": "lb" }
  ]
}
```

不同精度位的 AI 视为不同标识符（如 `3101` 与 `3102` 可同时出现），但同一完整
AI 仍受重复校验约束。

路径段必须成对，例如 `.../01/09501101530003/17` 会返回 `422`
（`UNPAIRED_PATH`）；同一 AI 不能重复，也不能同时出现在路径和查询参数中
（`DUPLICATE_AI`）。

## 错误响应

解析或校验失败返回 `422 Unprocessable Entity`，`detail` 中包含错误码、
字节偏移（`offset`，UTF-8 字节序）与预期规则（`expected`）：

```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"data": "0109501101530004"}'
```

```json
{
  "detail": {
    "error": "INVALID_CHECK_DIGIT",
    "message": "GTIN check digit mismatch: expected 3, found 4",
    "offset": 15,
    "expected": "Mod-10 check digit 3",
    "found": "4"
  }
}
```

错误码一览：

| 错误码                 | 说明                                                          |
| ---------------------- | ------------------------------------------------------------- |
| `EMPTY_INPUT`          | 输入为空（元素串为空，或 URI 路径/查询中没有任何 AI/值对）    |
| `UNEXPECTED_SEPARATOR` | 在应出现 AI 的位置遇到分隔符（仅元素串）                      |
| `INVALID_AI`           | 不是合法的数字 AI（元素串不足 2 位数字；URI 为非数字段/键）   |
| `UNSUPPORTED_AI`       | 不支持的 AI（仅支持 01/10/17/21 与 310n/320n）                |
| `INVALID_PRECISION`    | `310`/`320` 族缺少第 4 位精度位 n（缺失或为非数字字符）       |
| `FIELD_TOO_SHORT`      | 固定长度字段字符不足（含 310n/320n 的 6 位值不足）            |
| `FIELD_EMPTY`          | 可变长度字段为空                                              |
| `FIELD_TOO_LONG`       | 可变长度字段超过 20 字符（或固定长度字段超长，仅 URI）        |
| `INVALID_CHARACTER`    | 字符不符合该字段字符集                                        |
| `INVALID_CHECK_DIGIT`  | GTIN Mod-10 校验位不匹配                                      |
| `INVALID_DATE`         | 效期不是真实日期                                              |
| `UNPAIRED_PATH`        | Digital Link URI 路径段不是成对的 AI/值（仅 URI）             |
| `DUPLICATE_AI`         | AI 重复出现，或同时出现在路径与查询参数中（仅 URI）           |
| `INVALID_PERCENT_ENCODING` | `%XX` 不是合法十六进制转义或不是合法 UTF-8（仅 URI）      |

## 本地开发

```bash
pip install -r requirements-dev.txt
pytest                 # 运行测试
uvicorn app.main:app --reload --port 8080
```

## 项目结构

```
app/
  main.py   # FastAPI 应用与请求/响应模型
  gs1.py    # GS1 元素串 / Digital Link URI 解析与校验核心
tests/
  test_parse.py
Dockerfile
docker-compose.yml
requirements.txt      # 运行依赖
requirements-dev.txt  # 测试依赖
```
