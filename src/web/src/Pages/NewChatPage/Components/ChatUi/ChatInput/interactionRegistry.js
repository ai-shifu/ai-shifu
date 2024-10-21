// Global registry for interaction types
const interactionTypeRegistry = {};

// Function to register new interaction types
export const registerInteractionType = (type, component) => {
  interactionTypeRegistry[type] = component;
};

// Function to get a registered interaction type component
export const getInteractionComponent = (type) => {
  return interactionTypeRegistry[type];
};
