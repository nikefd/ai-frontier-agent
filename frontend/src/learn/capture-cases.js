export const captureCases=[
 {kind:'normal',id:'learn-conversation-v1',title:['正常阅读规划 · 3轮对话','Normal reading plan · 3 user turns']},
 {kind:'repair',id:'learn-search-v1',title:['故障修复与Explore · 7请求','Fault repair + Explore · 7 requests']},
 {kind:'skill',id:'learn-skill-v1',title:['Skill只读检查 · 5请求','Skill read-only check · 5 requests']},
];
export const captureCaseId=kind=>captureCases.find(c=>c.kind===kind)?.id;
