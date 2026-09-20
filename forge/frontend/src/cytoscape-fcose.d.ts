// cytoscape-fcose ships no type declarations. It is a layout extension
// registered via cytoscape.use(...). Its default export matches the cytoscape
// extension shape (cytoscape.Ext), which is what cytoscape.use accepts.
declare module "cytoscape-fcose" {
  import type cytoscape from "cytoscape";
  const fcose: cytoscape.Ext;
  export default fcose;
}
