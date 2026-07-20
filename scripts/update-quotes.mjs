import { mkdir, writeFile } from "node:fs/promises";

const sources = [
  {
    url: "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
    market: "上市",
    code: "Code",
    name: "Name",
    price: "ClosingPrice",
  },
  {
    url: "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
    market: "上櫃",
    code: "SecuritiesCompanyCode",
    name: "CompanyName",
    price: "Close",
  },
];

const number = value => Number(String(value ?? "").replaceAll(",", "").trim()) || 0;

const responses = await Promise.all(sources.map(async source => {
  const response = await fetch(source.url, { headers: { "User-Agent": "NiuNiuBudget/1.0" } });
  if (!response.ok) throw new Error(`${source.market} API ${response.status}`);
  return { source, rows: await response.json() };
}));

const quotes = {};
const dates = [];
for (const { source, rows } of responses) {
  for (const row of rows) {
    const code = String(row[source.code] ?? "").trim().toUpperCase();
    const price = number(row[source.price]);
    if (code && price > 0) quotes[code] = { price, name: row[source.name] ?? "", market: source.market };
    if (row.Date) dates.push(String(row.Date));
  }
}

await mkdir("assets", { recursive: true });
await writeFile("assets/quotes.json", JSON.stringify({
  date: dates.sort().at(-1) ?? "",
  generatedAt: new Date().toISOString(),
  quotes,
}));
console.log(`Updated ${Object.keys(quotes).length} quotes for ${dates.sort().at(-1) ?? "unknown date"}`);
