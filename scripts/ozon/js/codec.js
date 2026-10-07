// Ozon antibot `fp` codec (script v47_x):
//   fp = b64("Salted__" + salt + AES256CBC(PKCS7(XOR(utf8(JSON), token)), EvpKDF-md5(pw)))
//   with the 4-hex `seed` inserted in the middle of the base64 string;
//   pw = md5-chain(seed, token), chain differs per script build / challenge.
const crypto = require('crypto');

const md5 = (s) => crypto.createHash('md5').update(s).digest('hex');

// Password = n rounds of md5: md5(seed) -> md5(prev + token) -> md5(prev) ...; n varies per challenge.
const CHAIN_ROUNDS = [2, 3, 4, 5, 6, 7, 8];
const passwordFor = (rounds, seed, token) => {
  let h = md5(md5(seed) + token);
  for (let i = 2; i < rounds; i++) h = md5(h);
  return h;
};

function evpKdf(pw, salt) {
  let data = Buffer.alloc(0);
  let prev = Buffer.alloc(0);
  while (data.length < 48) {
    prev = crypto.createHash('md5').update(Buffer.concat([prev, Buffer.from(pw), salt])).digest();
    data = Buffer.concat([data, prev]);
  }
  return { key: data.subarray(0, 32), iv: data.subarray(32, 48) };
}

function xorToken(buf, token) {
  const t = Buffer.from(token, 'latin1');
  const out = Buffer.alloc(buf.length);
  for (let i = 0; i < buf.length; i++) out[i] = buf[i] ^ t[i % t.length];
  return out;
}

function splitSeed(fp) {
  const half = (fp.length - 4) / 2;
  return { seed: fp.slice(half, half + 4), b64: fp.slice(0, half) + fp.slice(half + 4) };
}

function decode(fp, token) {
  const { seed, b64 } = splitSeed(fp);
  const raw = Buffer.from(b64, 'base64');
  const salt = raw.subarray(8, 16);
  const ct = raw.subarray(16);
  let lastError;
  for (const chain of CHAIN_ROUNDS) {
    try {
      const { key, iv } = evpKdf(passwordFor(chain, seed, token), salt);
      const decipher = crypto.createDecipheriv('aes-256-cbc', key, iv);
      const json = xorToken(Buffer.concat([decipher.update(ct), decipher.final()]), token).toString('utf8');
      if (!json.startsWith('{"')) throw new Error('not json');
      return { seed, salt, json, chain };
    } catch (e) {
      lastError = e;
    }
  }
  throw lastError;
}

function encode(json, token, seed, salt, chain) {
  const { key, iv } = evpKdf(passwordFor(chain, seed, token), salt);
  const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
  const ct = Buffer.concat([cipher.update(xorToken(Buffer.from(json, 'utf8'), token)), cipher.final()]);
  const b64 = Buffer.concat([Buffer.from('Salted__'), salt, ct]).toString('base64');
  const half = b64.length / 2;
  return b64.slice(0, half) + seed + b64.slice(half);
}

// Decrypted plaintext may carry trailing garbage after the JSON: cut at the last parseable `}`.
function parseTrailing(text) {
  for (let i = text.length; (i = text.lastIndexOf('}', i)) > 0; i--) {
    try { return JSON.parse(text.slice(0, i + 1)); } catch (e) { /* keep scanning */ }
  }
  throw new Error('no JSON in decrypted fp');
}

module.exports = { decode, encode, splitSeed, parseTrailing };
