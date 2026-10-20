(function(){
 var d=document.documentElement,b=document.getElementById('theme-toggle'),meta=document.querySelector('meta[name="theme-color"]');
 var mq=window.matchMedia?matchMedia('(prefers-color-scheme: dark)'):null;
 var order=['auto','light','dark'],names={auto:'auto (matches your device)',light:'light',dark:'dark'};
 function apply(p){
  var t=p==='auto'?(mq&&mq.matches?'dark':'light'):p;
  d.setAttribute('data-theme-pref',p);d.setAttribute('data-theme',t);
  if(meta)meta.setAttribute('content',t==='dark'?'#1C1A17':'#F6F3EC');
  var next=order[(order.indexOf(p)+1)%3],l='Theme: '+names[p]+'. Switch to '+next+'.';
  b.setAttribute('aria-label',l);b.title=l;
 }
 b.addEventListener('click',function(){
  var p=order[(order.indexOf(d.getAttribute('data-theme-pref')||'auto')+1)%3];
  try{p==='auto'?localStorage.removeItem('theme'):localStorage.setItem('theme',p)}catch(e){}
  apply(p);
 });
 if(mq){var f=function(){if(d.getAttribute('data-theme-pref')==='auto')apply('auto')};mq.addEventListener?mq.addEventListener('change',f):mq.addListener(f);}
 window.addEventListener('storage',function(e){if(e.key==='theme')apply(e.newValue==='light'||e.newValue==='dark'?e.newValue:'auto')});
 apply(d.getAttribute('data-theme-pref')||'auto');
})();
