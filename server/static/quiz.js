/* Soru ekranı.
   Doğru cevap sunucuda tutulur; burada yalnızca görünen şık sırası bilinir.
   Çalışma modunda doğru cevapta soru kendiliğinden geçer, yanlışta cevap gösterilir. */
(function(){
"use strict";

const root  = document.getElementById('quizRoot');
const stage = document.getElementById('stage');
const pfill = document.getElementById('pfill');
const qiEl  = document.getElementById('qi');

const RUN   = root.dataset.run;
const TOTAL = +root.dataset.total;
const MODE  = root.dataset.mode;
const KEYS  = ['A','B','C','D','E'];

let idx = Math.min(+root.dataset.start || 0, TOTAL - 1);
let cur = null;        // ekrandaki soru
let shown = null;      // {correct, correct_pos, pos} — cevap verildiyse
let busy = false;
let shownAt = 0;
let timer = null;

const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function progress(){
  qiEl.textContent = Math.min(idx + 1, TOTAL);
  pfill.style.width = (idx / TOTAL * 100) + '%';
}

async function load(){
  progress();
  if (idx >= TOTAL) return finish();
  stage.setAttribute('aria-busy', 'true');
  let d;
  try{
    const r = await fetch('/api/tur/' + RUN + '/soru/' + idx);
    if (r.status === 401) return location.href = '/giris';
    d = await r.json();
  }catch(e){
    stage.innerHTML = '<div class="empty">Bağlantı kurulamadı.<br>' +
      '<button class="btn ghost auto" style="margin-top:12px" onclick="location.reload()">Tekrar dene</button></div>';
    return;
  }
  if (d.done) return finish();
  cur = d;
  shown = d.answered || null;
  shownAt = Date.now();
  draw();
  stage.removeAttribute('aria-busy');
}

function draw(){
  const q = cur;
  const reveal = shown && MODE === 'calisma';

  const badges =
    (q.needs_figure ? '<span class="badge fig" title="Soru bir şekle atıf yapıyor; görsel bankada yok">şekil gerekli</span>' : '') +
    (q.generated ? '<span class="badge gen" title="Ders notundan üretilmiş — gerçek sınav sorusu değil">üretilmiş</span>' : '') +
    (q.flagged ? '<span class="badge flag" title="Kaynakta Attention! işaretli — cevabı tartışmalı">tartışmalı</span>' : '');

  const opts = q.options.map((o, i) => {
    let cls = 'opt', mark = '';
    if (reveal){
      if (i === shown.correct_pos){ cls += ' right'; mark = 'DOĞRU'; }
      else if (i === shown.pos){ cls += ' wrong'; mark = 'SEÇTİN'; }
    } else if (shown && i === shown.pos){ cls += ' sel'; }
    return '<button class="' + cls + '" type="button" data-pos="' + i + '"' +
      (shown ? ' disabled' : '') + '>' +
      '<span class="k">' + KEYS[i] + '</span><span>' + esc(o.text) + '</span>' +
      (mark ? '<span class="m">' + mark + '</span>' : '') + '</button>';
  }).join('');

  let verdict = '';
  if (reveal){
    verdict = shown.correct
      ? '<div class="verdict ok"><span class="tag">Doğru</span>' +
        '<span class="txt">Sonraki soruya geçiliyor…</span></div>'
      : '<div class="verdict bad"><span class="tag">Yanlış</span>' +
        '<span class="txt">Doğru cevap: <b>' + esc(shown.correct_text || '') + '</b>' +
        '<span class="s">Yanlış defterine yazıldı</span></span></div>';
  }

  const last = idx === TOTAL - 1;
  stage.innerHTML =
    '<div class="card">' +
      '<div class="qhead"><span class="lbl">' + esc(q.subject_code) + '</span>' +
        '<span class="who">' + esc(q.sec_name || '') + '</span>' +
        '<span class="sp"></span>' + badges +
        '<span class="lbl num">ID ' + q.id + '</span></div>' +
      '<div class="qtext">' + esc(q.text) + '</div>' +
      '<div class="opts">' + opts + '</div>' + verdict +
    '</div>' +
    '<div class="actions">' +
      '<button class="btn" id="next"' + (shown ? '' : ' disabled') + '>' +
        (last ? 'Bitir ve sonucu gör' : (reveal && !shown.correct ? 'Anladım, devam' : 'Sonraki soru')) +
      '</button>' +
      (shown ? '' : '<button class="btn ghost" id="skip">Atla</button>') +
    '</div>';

  stage.querySelectorAll('.opt').forEach(b =>
    b.addEventListener('click', () => answer(+b.dataset.pos)));
  const nx = document.getElementById('next');
  if (nx) nx.onclick = () => go();
  const sk = document.getElementById('skip');
  if (sk) sk.onclick = () => go();
}

async function answer(pos){
  if (busy || shown) return;
  busy = true;
  let d;
  try{
    const r = await fetch('/api/tur/' + RUN + '/cevap', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ qid: cur.id, pos: pos, ms: Date.now() - shownAt })
    });
    if (r.status === 401) return location.href = '/giris';
    d = await r.json();
  }catch(e){
    busy = false;
    return;
  }
  busy = false;
  if (d.error) return;
  shown = { pos: pos, correct: d.correct, correct_pos: d.correct_pos, correct_text: d.correct_text };
  draw();
  clearTimeout(timer);
  if (MODE === 'sinav') timer = setTimeout(go, 160);
  else if (d.correct) timer = setTimeout(go, 620);
}

function go(){
  clearTimeout(timer);
  idx++;
  window.scrollTo({ top: 0, behavior: 'smooth' });
  load();
}

async function finish(){
  try{ await fetch('/api/tur/' + RUN + '/bitir', { method: 'POST' }); }catch(e){}
  location.href = '/sonuc/' + RUN;
}

document.addEventListener('keydown', e => {
  if (e.target.matches('input, select, textarea')) return;
  if (e.key >= '1' && e.key <= '5'){
    const i = +e.key - 1;
    if (cur && i < cur.options.length && !shown){ answer(i); e.preventDefault(); }
  } else if (e.key === 'Enter' || e.key === 'ArrowRight'){
    if (shown){ go(); e.preventDefault(); }
  }
});

load();
})();
