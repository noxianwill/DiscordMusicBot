const routes = new Map();
let currentViewCleanup = null;

export function registerRoute(hash, viewModule) {
  routes.set(hash, viewModule);
}

export async function navigate(hash) {
  location.hash = hash;
}

export async function handleRouteChange(appState) {
  const hash = location.hash.split('?')[0] || '#dashboard';

  if (currentViewCleanup && typeof currentViewCleanup === 'function') {
    currentViewCleanup();
    currentViewCleanup = null;
  }

  const container = document.getElementById('view-container');
  if (!container) return;

  const viewModule = routes.get(hash) || routes.get('#dashboard');
  if (viewModule && typeof viewModule.render === 'function') {
    currentViewCleanup = await viewModule.render(container, appState);
  }

  // Update active tab in navbar
  const navLinks = document.querySelectorAll('.nav-link');
  for (const link of navLinks) {
    if (link.getAttribute('href') === hash) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  }
}

