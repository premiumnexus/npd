document.addEventListener('DOMContentLoaded',()=>{
  const update=()=>document.querySelectorAll('[data-elapsed-start]').forEach(element=>{
    const started=Date.parse(element.dataset.elapsedStart);
    if(!Number.isFinite(started)) return;
    const minutes=Math.max(0,Math.floor((Date.now()-started)/60000));
    const days=Math.floor(minutes/1440),hours=Math.floor(minutes%1440/60),remaining=minutes%60;
    const parts=[];
    if(days)parts.push(`${days} өдөр`);
    if(hours)parts.push(`${hours} цаг`);
    if(remaining)parts.push(`${remaining} минут`);
    element.textContent=parts.join(' ') || '1 минутаас бага';
  });
  update();setInterval(update,60000);
});
