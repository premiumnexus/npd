document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('[data-launch-checkpoint]').forEach(form=>{
    const actual=form.elements.namedItem('actual_apsd');
    const target=form.elements.namedItem('target_apsd');
    const output=form.querySelector('[data-apsd-achievement]');
    const result=form.elements.namedItem('sample_result');
    const action=form.elements.namedItem('action_plan');
    const actionWrapper=form.querySelector('[data-checkpoint-actions]');
    const editable=form.dataset.editable==='true';
    const writeoff=form.elements.namedItem('actual_writeoff_percent');
    const writeoffOutput=form.querySelector('[data-writeoff-status]');
    const read=input=>{
      if(!input || input.value.trim()==='' || !input.validity.valid) return null;
      const value=Number(input.value);
      return Number.isFinite(value) && value>=0?value:null;
    };
    const updateAchievement=()=>{
      const observed=read(actual),goal=read(target);
      const percent=observed!==null && goal!==null && goal>0?observed/goal*100:null;
      output.value=percent===null?'—':percent.toFixed(2)+'%';
      output.dataset.status=percent===null?'Pending':observed>=goal?'Green':observed*100>=goal*80?'Amber':'Red';
    };
    const updateAction=()=>{
      const visible=['conditional','outside'].includes(result.value);
      const required=result.value==='outside';
      actionWrapper.hidden=!visible;
      action.required=editable && required;
      action.disabled=!editable || !visible;
      const star=form.querySelector('[data-checkpoint-action-star]');
      if(star) star.hidden=!required;
    };
    const updateWriteoff=()=>{
      if(!writeoffOutput) return;
      const value=read(writeoff),raw=writeoffOutput.dataset.target;
      const goal=raw.trim()===''?null:Number(raw);
      const status=value===null || goal===null || !Number.isFinite(goal)?'Pending':value<=goal?'Green':'Red';
      writeoffOutput.dataset.status=status;
      writeoffOutput.value={Pending:'—',Green:'Ногоон',Red:'Улаан'}[status];
    };
    actual.addEventListener('input',updateAchievement);
    result.addEventListener('change',updateAction);
    if(writeoff) writeoff.addEventListener('input',updateWriteoff);
    updateAchievement();
    updateAction();
    updateWriteoff();
  });
});
