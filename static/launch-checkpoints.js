document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('[data-launch-checkpoint]').forEach(form=>{
    const actual=form.elements.namedItem('actual_apsd');
    const target=form.elements.namedItem('target_apsd');
    const output=form.querySelector('[data-apsd-achievement]');
    const result=form.elements.namedItem('sample_result');
    const action=form.elements.namedItem('action_plan');
    const actionWrapper=form.querySelector('[data-checkpoint-actions]');
    const editable=form.dataset.editable==='true';
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
      const required=['conditional','outside'].includes(result.value);
      actionWrapper.hidden=!required;
      action.required=editable && required;
      action.disabled=!editable || !required;
    };
    actual.addEventListener('input',updateAchievement);
    result.addEventListener('change',updateAction);
    updateAchievement();
    updateAction();
  });
});
