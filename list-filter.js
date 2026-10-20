/* Filter for post lists (/features/, /archive/). Rows are .fi[data-type]; buttons are .filter [data-f].
   Without JS the filter bar stays hidden and every row shows. */
(function(){
 document.querySelectorAll('[data-filter-list]').forEach(function(l){
  var bar=l.querySelector('.filter'),bs=bar?bar.querySelectorAll('button'):[],rows=l.querySelectorAll('.fi'),em=l.querySelector('.empty');
  function set(v){
   var n=0;
   rows.forEach(function(r){var on=v==='all'||r.getAttribute('data-type')===v;r.hidden=!on;r.classList.toggle('first-visible',on&&n===0);if(on)n++});
   bs.forEach(function(b){b.setAttribute('aria-pressed',b.getAttribute('data-f')===v?'true':'false')});
   if(em){em.hidden=n>0;em.textContent=em.getAttribute('data-'+v)||em.getAttribute('data-none')||'Nothing here yet.'}
  }
  bs.forEach(function(b){b.addEventListener('click',function(){set(b.getAttribute('data-f'))})});
  if(bar)bar.hidden=false;
  set('all');
 });
})();
