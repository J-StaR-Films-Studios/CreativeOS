/** Identify project actions by filesystem path, never by a conflicting title. */
export function findProjectForItem(projects, item, includeDescendants = false) {
  if (!item) return null;
  if (!item.path) {
    return projects.find(project => project.name === item.name || project.slug === item.name) || null;
  }
  const path = item.path.replace(/\\/g, "/").replace(/\/$/, "").toLowerCase();
  const exact = projects.find(project => project.path &&
    project.path.replace(/\\/g, "/").replace(/\/$/, "").toLowerCase() === path);
  if (exact || !includeDescendants) return exact || null;
  return projects.find(project => project.path && path.startsWith(
    `${project.path.replace(/\\/g, "/").replace(/\/$/, "").toLowerCase()}/`
  )) || null;
}
