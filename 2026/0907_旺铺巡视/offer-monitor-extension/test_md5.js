// 本地校验用: node test_md5.js
const fs = require("fs");
eval(fs.readFileSync(__dirname + "/md5.js", "utf8"));

const cases = [
  ["抓包签名对", 'ba83020e92227c3a9c5036142dcef178&1788786847907&12574478&{"memberId":"b2b-319033927380e11","sortType":"wangpu_score","pageNum":1,"pageSize":300}', "0c341bc9e34c648c0a45cfdd24007d05"],
  ["空串", "", "d41d8cd98f00b204e9800998ecf8427e"],
  ["abc", "abc", "900150983cd24fb0d6963f7d28e17f72"],
  ["The quick brown fox", "The quick brown fox jumps over the lazy dog", "9e107d9d372bb6826bd81d3542a419d6"],
  ["中文", "雨伞", "3bd9d5ab6cf67d327232e0bbb33e16a2"],
];

let allOk = true;
for (const [name, input, want] of cases) {
  const got = md5(input);
  const ok = got === want;
  if (!ok) allOk = false;
  console.log(ok ? "PASS" : "FAIL", name, got, ok ? "" : "(want " + want + ")");
}
process.exit(allOk ? 0 : 1);
