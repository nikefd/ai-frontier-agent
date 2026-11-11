import { inspectRequest } from './inspect-request.js';
// A supplied request is evidence of definitions/results, not proof of execution.
export function associateStream(report, source) {
  const request = inspectRequest(source, report.protocol);
  return report.calls.map(call => ({
    id: call.id, name: call.name,
    definitions: request.tools.filter(tool => tool.name === call.name).map(tool => tool.path),
    results: request.results.filter(result => call.id && result.id === call.id).map(result => result.item),
  }));
}
