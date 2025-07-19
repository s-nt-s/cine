const isLocal = ["", "localhost"].includes(document.location.hostname);
const $$ = (slc) => Array.from(document.querySelectorAll(slc));
const DB = new Db();

function chunkArray(arr, chunkSize) {
  const result = [];
  let chunk;
  for (let i = 0; i < arr.length; i += chunkSize) {
    chunk = arr.slice(i, i + chunkSize);
    if (chunk.length) result.push(chunk);
  }
  return result;
}

class FormQuery {
  static ALIAS = Object.freeze({})
  static form() {
    const d = {
      range: {},
    };
    document.querySelectorAll("input[id], select[id]").forEach((n) => {
      if (n.disabled) return;
      if (/_(max|min)$/.test(n.id)) return;
      const v = getVal(n.id);
      if (v === false) return;
      const nm = n.getAttribute("name");
      if (nm != null) {
        if (!Array.isArray(d[nm])) d[nm] = [];
        d[nm].push(v);
        return;
      }
      d[n.id] = v;
    });
    d.range = getRanges(...FormQuery.RANGE.filter(r => (document.getElementById(r + '_min')?.disabled) === false));
    return d;
  }
  static __form_to_query() {
    const form = FormQuery.form();
    const qr = [];
    Object.entries(form).forEach(([k, v]) => {
      if (FormQuery.DEF_FLAGS.includes(v)) return;
      if (FormQuery.FLAGS.includes(v)) {
        qr.push(v);
        return;
      }
      if (typeof v === "object" && Object.keys(v).length === 0) return;
      if (typeof v == "string") v = encodeURIComponent(v);
      if (v === true) {
        qr.push(k);
        return;
      }
      qr.push(k + "=" + v);
    });
    Object.entries(form.range).forEach(([k, v]) => {
      const n = document.getElementById(k + "_max");
      if (
        Number(n.getAttribute("min")) == v.min &&
        Number(n.getAttribute("max")) == v.max
      )
        return;
      if (FormQuery.RANGE.includes(k) && MX[k] != null) {
        if (k == "price" && v.min == 0) return qr.push(k + "=" + v.max);
        if (v.max == MX[k]) return qr.push(k + "=" + v.min);
      }
      qr.push(k + "=" + v.min + "-" + v.max);
    });
    const query = qr.join("&")
    return FormQuery.REV_QUERY[query] ?? query;
  }
  static form_to_query() {
    let query = "?" + FormQuery.__form_to_query();
    if (query == "?") query = "";
    if (document.location.search == query) return;
    const url = document.location.href.replace(/\?.*$/, "");
    history.pushState({}, "", url + query);
  }
  static query_to_form() {
    const query = FormQuery.query();
    if (query == null) return;
    Object.entries(query).forEach(([k, v]) => {
      if (document.getElementById(k) == null) return;
      setVal(k, v);
    });
    const _set_rank_val = (n) => {
      const [id, k] = n.id.split("_");
      if (query.range == null || query.range[id] == null || query.range[id][k] == null) {
        n.value = n.getAttribute(k);
        return;
      }
      n.value = query.range[id][k];
    }
    $$("input[id$=_min],input[id$=_max]").forEach(_set_rank_val);
    if (query.range)
      Object.entries(query.range).forEach(([k, v]) => {
        setVal(k + "_min", v["min"]);
        setVal(k + "_max", v["max"]);
      });
  }
  static query() {
    const search = (() => {
      const q = document.location.search.replace(/^\?/, "")
      if (q.length == 0) return null;
      return FormQuery.ALIAS[q] ?? q;
    })();
    const d = {
      range: {},
    };
    if (search == null) return d;
    search.split("&").forEach((i) => {
      const [k, v] = FormQuery.__get_kv(i);
      if (k == null) return;
      if (typeof v == "object") {
        d.range[k] = v;
        return;
      }
      if (Array.isArray(d[k])) d[k] = v.split("+").map((t) => decodeURIComponent(t));
      else d[k] = v;
    });
    return d;
  }
  static __get_kv(kv) {
    const tmp = kv.split("=").flatMap((i) => {
      i = i.trim();
      return i.length == 0 ? [] : i;
    });
    if (tmp.length == 0) return [null, null];
    if (tmp.length > 2 || tmp[0].length == 0) return [null, null];
    const k = tmp[0];
    if (FormQuery.DEF_FLAGS.includes(k) || FormQuery.FLAGS.includes(k)) {
      const opt = document.querySelector(
        'select option[value="' + k + '"]'
      );
      return [opt.closest("select[id]").id, k];
    }
    if (!isNaN(Number(k))) return [null, null];
    if (tmp.length == 1) {
      const opt = document.querySelectorAll(
        'select option[value="' + k + '"]'
      );
      if (opt.length == 1) {
        return [opt[0].closest("select[id]").id, k];
      }
      return [k, true];
    }
    let v = tmp[1];
    if (FormQuery.RANGE.includes(k) && v.match(/^\d+$/) && MX[k] != null) {
      v = v + '-' + MX[k];
    }
    const n = Number(v);
    if (!isNaN(n)) return [k, n];
    if (v.match(/^\d+-\d+$/)) {
      const [_min, _max] = v
        .split("-")
        .map((i) => Number(i))
        .sort((a, b) => a - b);
      return [k, { min: _min, max: _max }];
    }
    return [k, v];
  }
}
FormQuery.REV_QUERY = Object.freeze(Object.fromEntries(Object.entries(FormQuery.ALIAS).map(([k, v]) => [v, k])))


function getVal(id) {
  const elm = document.getElementById(id);
  if (elm == null) {
    console.log("No se ha encontrado #" + id);
    return null;
  }
  if (elm.tagName == "INPUT" && elm.getAttribute("type") == "checkbox") {
    if (elm.checked === false) return false;
    const v = elm.getAttribute("value");
    if (v != null) return v;
    return elm.checked;
  }
  const val = (elm.value ?? "").trim();
  if (val.length == 0) return null;
  const tp = elm.getAttribute("data-type") || elm.getAttribute("type");
  if (tp == "number") {
    const num = Number(val);
    if (isNaN(num)) return null;
    return num;
  }
  return val;
}

function setVal(id, v) {
  const elm = document.getElementById(id);
  if (elm == null) {
    console.log("No se ha encontrado #" + id);
    return null;
  }
  if (elm.tagName == "INPUT" && elm.getAttribute("type") == "checkbox") {
    if (arguments.length == 1) v = elm.defaultChecked;
    elm.checked = v === true;
    return;
  }
  if (arguments.length == 1) {
    v = elm.defaultValue;
  }
  elm.value = v;
}

function getRanges() {
  const rgs = {};
  Array.from(arguments).forEach((k) => {
    let mn = getVal(k + "_min");
    let mx = getVal(k + "_max");
    if (mn == null || mx == null) return;
    rgs[k] = { min: mn, max: mx };
  });
  return rgs;
}

function ifLocal() {
  if (!isLocal) return;
  const mkA = (url) => {
    const a = document.createElement("a");
    const spl = url.split(/\/|\./);
    a.textContent = spl[spl.length-2];
    a.href = url;
    return a;
  }
  const gId = (s) => {
    while (s.endsWith("/")) s = s.substring(0, s.length-1);
    const spl = s.split("/");
    return spl[spl.length-1];
  }
  document.querySelectorAll("div.film").forEach(i=>{
    const p = i.querySelector("p");
    const imdb = i.querySelector("a.imdb");
    const rtve = i.querySelector("a.title");
    if (rtve) p.append(" ", mkA(`../rec/rtve/${gId(rtve.href)}.json`));
    if (imdb) p.append(" ", mkA(`../rec/imdb/${gId(imdb.href)}.json`));
  })
}


function setOrder() {
  const flags = new Set();
  const default_flags = new Set();
  document.querySelectorAll('select[data-type="flag"]').forEach((s) => {
    const arr_options = Array.from(s.options);
    const defVal = arr_options.filter(o => o.getAttribute("selected") != null)[0].value;
    s.setAttribute("data-current", defVal);
    default_flags.add(defVal);
    const vals = arr_options.flatMap(o => [null, "", defVal].includes(o.value)?[]:o.value);
    vals.forEach(x => flags.add(x));
  });
  FormQuery.FLAGS = Object.freeze(Array.from(flags));
  FormQuery.DEF_FLAGS = Object.freeze(Array.from(default_flags));
}


document.addEventListener(
  "DOMContentLoaded",
  () => {
    FormQuery.RANGE = Object.freeze(Array.from(new Set(
      $$("input[id$=_max],input[id$=_min]").filter(n => !n.disabled).map((n) =>
        n.id.replace(/_(max|min)$/, "")
      ))));
    setOrder();
    ifLocal();
    FormQuery.query_to_form();
    document.querySelectorAll("input, select").forEach((i) => {
      i.addEventListener("change", onChange);
    });
    onChange();
    document.querySelectorAll("a.poster").forEach((a) => {
      a.addEventListener("click", (event) => {
        if (!document.body.classList.contains("cuadricula")) return;
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        a.closest("div.film").classList.toggle("expand");
      });
    });
    const urls = $$("a.title").map(i=>i.href);
    chunkArray(urls, 100).forEach(chunk=>{
      DB.selectTableWhere('m3u8', 'url', ...chunk).then((arr) => {
        arr.forEach(o=>{
           document.querySelectorAll(`a[href="${o.url}"]`).forEach(a=>{
            const m3u8 = o.m3u8;
            const isPoster = a.classList.contains("poster");
            a.addEventListener('click', (event)=>{
              //if (isPoster && document.body.classList.contains("cuadricula")) {
              //  requestFullscreen(a.closest("div.film"));
              //} else 
              if (mkVideo(m3u8, true) == null) return;
              event.preventDefault();
              event.stopPropagation();
              event.stopImmediatePropagation();
            });
          });
        })
      });
    })
  },
  false
);

function requestFullscreen (v) {
  if (v.requestFullscreen) return v.requestFullscreen();
  if (v.webkitRequestFullscreen) return v.webkitRequestFullscreen();
  if (v.mozRequestFullScreen) return v.mozRequestFullScreen();
  if (v.msRequestFullscreen) return v.msRequestFullscreen();
}

function mkVideo(url, fireByUser) {
  fireByUser = fireByUser===true;
  let div = document.getElementById("video");
  if (div) div.remove();
  if (url == null) return null;
  const video = document.createElement("video");
  if (video==null) return null;
  video.controls = true;
  video.autoplay = true;
  video.playsInline = true;
  video.muted = !fireByUser;
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = url;
  } else {
    const hls = new Hls();
    hls.loadSource(url);
    hls.attachMedia(video);
  }

  div = document.createElement("div");
  div.id = "video";
  const button = document.createElement("button");
  button.textContent="Cerrar video";
  button.addEventListener("click", ()=>mkVideo());
  div.appendChild(video);
  div.appendChild(button);
  document.body.insertBefore(div, document.body.firstChild);
  if (fireByUser) video.play().then(() => {
    requestFullscreen(video)
  });
  else {
    const events = ['mousemove', 'keydown', 'click'];
    const onFirstUserInteraction = () => {
      console.log("onFirstUserInteraction");
      video.muted = false;
      events.forEach(e=> window.removeEventListener(e, onFirstUserInteraction));
    }
    events.forEach(e=>window.addEventListener(e, onFirstUserInteraction));
  }
  return video;
}

function ifChange(form, id, fnc) {
  const o = document.getElementById(id);
  const newVal = form[id];
  const oldVal = o.getAttribute("data-current");
  if (form[id] == oldVal) return;
  console.log(id, oldVal, "->", newVal);
  fnc(newVal, oldVal);
  o.setAttribute("data-current", newVal);
}


function onChange() {
  const div = document.getElementById("films");
  const form = FormQuery.form();

  ifChange(form, "view", (newVal, oldVal) => {
    document.body.classList.remove(oldVal);
    document.body.classList.add(newVal);
  });
  ifChange(form, "order", (newVal, oldVal) => {
    ORDER.get(newVal).forEach(i => div.append(document.getElementById(i)));
  });

  FormQuery.form_to_query();
}
