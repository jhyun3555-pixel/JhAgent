export const COLORS = {completed:'#55deb2',running:'#55c8de',queued:'#55c8de',waiting_approval:'#ae9aff',waiting_customer:'#ae9aff',blocked:'#edbc6a',no_action:'#778ba5',failed:'#f07f87',cancelled:'#637185'};
export function sparkline(values, color='#55deb2') {
  const max=Math.max(1,...values), points=values.map((v,i)=>`${i*100/Math.max(1,values.length-1)},${31-v/max*25}`).join(' ');
  return `<svg class="metric-spark" viewBox="0 0 100 35" preserveAspectRatio="none" aria-hidden="true"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
}
export function scatter(snapshot) {
  const W=650,H=210,left=38,right=15,top=13,bottom=25;
  const jobs=snapshot.jobs.filter(j=>j.status!=='queued'), max=Math.max(10,Math.ceil(Math.max(0,...jobs.map(j=>j.duration_ms))/5000)*5), duration=snapshot.minutes*60;
  const grid=Array.from({length:5},(_,i)=>{const y=top+(H-top-bottom)*i/4;return `<line class="gridline" x1="${left}" x2="${W-right}" y1="${y}" y2="${y}"/><text class="axis" x="${left-9}" y="${y+3}" text-anchor="end">${(max*(1-i/4)).toFixed(max>20?0:1)}s</text>`}).join('');
  const axes=Array.from({length:5},(_,i)=>{const x=left+(W-left-right)*i/4;const date=new Date((snapshot.now-duration+duration*i/4)*1000);return `<text class="axis" x="${x}" y="${H-4}" text-anchor="${i===0?'start':i===4?'end':'middle'}">${date.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false})}</text>`}).join('');
  const points=jobs.map(j=>{const x=left+Math.max(0,Math.min(1,(j.created_at-snapshot.now+duration)/duration))*(W-left-right),y=H-bottom-Math.min(max,j.duration_ms/1000)/max*(H-top-bottom);return `<circle class="point" data-job="${j.id}" tabindex="0" role="button" aria-label="${j.id} 처리 단계 보기" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.9" fill="${COLORS[j.status]||COLORS.completed}" opacity=".85"><title>${j.id} · ${(j.duration_ms/1000).toFixed(2)}초</title></circle>`}).join('');
  return `<svg class="scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="실제 저장된 작업의 생성 시간 대비 agent 처리 시간 분포">${grid}${axes}${points}</svg>`;
}
