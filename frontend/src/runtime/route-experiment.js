// Domain model: deterministic states of the isolated boot reproduction, no DOM or IO.
export const routes = ['/', '/runtime', '/experiments'];
export function routeExperiment({ path = '/runtime', earlyShell = false, earlyPublic = false } = {}) {
 if (!routes.includes(path)) throw new RangeError('Unknown experiment route');
 const landing = path === '/';
 const publicRoute = path === '/runtime';
 const pending = { landing: earlyShell ? landing : true, publicLoads: Number(publicRoute && earlyPublic), privateLoads: 0 };
 const settled = { landing, publicLoads: Number(publicRoute), privateLoads: Number(path === '/experiments') };
 return { pending, settled, checks: [
  { id: 'shell', pass: !routeExperimentState('/runtime', earlyShell, earlyPublic).landing },
  { id: 'public', pass: routeExperimentState('/runtime', earlyShell, earlyPublic).publicLoads === 1 },
  { id: 'private', pass: pending.privateLoads === 0 && (path !== '/experiments' || settled.privateLoads === 1) },
  { id: 'root', pass: path !== '/' || pending.landing && settled.publicLoads === 0 && settled.privateLoads === 0 },
 ] };
}
function routeExperimentState(path, earlyShell, earlyPublic) {
 return { landing: earlyShell ? path === '/' : true, publicLoads: Number(path === '/runtime' && earlyPublic) };
}
export function experimentCode({ earlyShell, earlyPublic }) {
 return [
  `state.landing = ${earlyShell ? "path === '/'" : 'true'};`,
  ...(earlyPublic ? ["if (path === '/runtime') loadPublic();"] : []),
  'await initAuth();',
  ...(!earlyShell ? ["state.landing = path === '/';"] : []),
  ...(!earlyPublic ? ["if (path === '/runtime') loadPublic();"] : []),
  "if (path !== '/' && path !== '/runtime') loadPrivate();",
 ].join('\n');
}
