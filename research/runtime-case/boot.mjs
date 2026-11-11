// Minimal reproduction of the site's landing-page flash and auth sequencing.
export async function boot({ path, state, initAuth, loadPublic, loadPrivate }) {
  state.landing = true;
  await initAuth();
  state.landing = path === '/';
  if (path === '/runtime') loadPublic();
  else if (path !== '/') loadPrivate();
}
