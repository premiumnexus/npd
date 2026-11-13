document.addEventListener('DOMContentLoaded',()=>{
  const root=document.querySelector('#recipe-calculator');
  if(!root) return;
  const rows=[...root.querySelectorAll('[data-recipe-row]')];
  const add=root.querySelector('[data-recipe-add]');
  if(add) {
    const ingredient=add.querySelector('[name="ingredient"]'),price=add.querySelector('[name="unit_price"]');
    const prices=()=>JSON.parse(ingredient.dataset.prices || '{}');
    const preview=()=>{
      const grams=Number(add.querySelector('[name="net_grams"]').value);
      const factor=Number(add.querySelector('[name="yield_factor"]').value || 1);
      const rate=price.value===''?Number(prices()[ingredient.value]):Number(price.value);
      const valid=add.checkValidity() && factor>=0.01 && factor<=1 && Number.isFinite(rate);
      add.querySelector('[data-new-line-cost]').textContent=valid?'₮'+(grams/1000/factor*rate).toFixed(0):'—';
    };
    ingredient.addEventListener('change',()=>{price.value=prices()[ingredient.value] || '';preview();});
    add.addEventListener('input',preview);
    preview();
  }
  const read=(row,name,fallback)=>{
    const input=row.querySelector(`[name="${name}"]`);
    if(!input) return Number(fallback);
    if(input.value.trim()==='' || !input.validity.valid) return null;
    return Number(input.value);
  };
  const update=()=>{
    let total=0,valid=true;
    rows.forEach(row=>{
      const grams=read(row,'net_grams',Number(row.dataset.quantity)*1000);
      const yieldFactor=read(row,'yield_factor',row.dataset.yield);
      const price=read(row,'unit_price',row.dataset.price);
      const cost=grams===null || yieldFactor===null || yieldFactor<=0 || price===null?null:grams/1000/yieldFactor*price;
      row.querySelector('[data-line-cost]').textContent=cost===null?'—':cost.toFixed(0);
      if(cost===null) valid=false; else total+=cost;
    });
    const packaging=root.querySelector('[name="packaging"]');
    const pack=packaging?(packaging.validity.valid?Number(packaging.value):NaN):Number(root.querySelector('[data-packaging]').dataset.packaging);
    total+=pack;
    valid=valid && Number.isFinite(total);
    if(rows.length===0){
      const typed=root.querySelector('[name="typed_cogs"]');
      const raw=typed?typed.value:root.dataset.typedCogs;
      if(raw!==undefined && raw.trim()!==''){
        total=Number(raw);
        valid=Number.isFinite(total) && total>=0 && (!typed || typed.validity.valid);
      }else{
        valid=valid && pack>0;
      }
    }
    root.querySelector('[data-recipe-total]').textContent=valid?'₮'+total.toFixed(0):'—';
    const limit=Number(root.dataset.limit),band=Number(root.dataset.band);
    const gap=valid && limit>0?(total/limit-1)*100:null;
    const tolerance=Number.EPSILON*Math.max(1,Math.abs(total),Math.abs(limit))*8;
    const status=gap===null?'Pending':total-limit<=tolerance?'Green':total-limit*(1+band/100)<=tolerance?'Amber':'Red';
    const label={Green:'Ногоон',Amber:'Шар',Red:'Улаан',Pending:'Хүлээгдэж байна'}[status];
    root.querySelector('[data-recipe-gap]').textContent=gap===null?'—':gap.toFixed(1)+'%';
    root.querySelectorAll('[data-recipe-status], [data-cogs-status-field]').forEach(element=>{
      if(element.tagName==='INPUT') element.value=label;
      else element.textContent=label;
      element.dataset.cogsStatus=status;
    });
    const gapField=root.querySelector('[name="cogs_gap_percent"]');
    if(gapField) gapField.value=gap===null?'':gap.toFixed(1);
    root.querySelector('[data-recipe-director]').textContent=gap===null?'—':status==='Red'?'Тийм':'Үгүй';
  };
  root.addEventListener('input',update);
  update();
});
