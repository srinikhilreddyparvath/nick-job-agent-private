export const roleFamilyLabels: Record<string, string> = {
  RESEARCH_AI: "Research / AI", DATA_SCIENCE: "Data science", PRODUCT_MANAGEMENT: "Product management",
  CLINICAL_RESEARCH: "Clinical research", PUBLIC_HEALTH: "Public health", HEALTHCARE_OPERATIONS: "Healthcare operations",
  RESEARCH: "Research", SOFTWARE_ENGINEERING: "Software engineering", INFORMATION_TECHNOLOGY: "Information technology", UNKNOWN: "Other roles",
};
export const roleFamilyLabel = (family: string) => roleFamilyLabels[family] ?? family.replaceAll("_", " ");
