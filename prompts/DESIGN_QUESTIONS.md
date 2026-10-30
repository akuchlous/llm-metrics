# Design-question requirements

Every numbered implementation step must create role-specific design questions grounded in that step's actual implementation.

For Step `NN`, create:

```text
design-questions/NN/
├── lead-engineer.md
├── principal-engineer.md
├── senior-manager.md
└── director.md
```

Follow the format established by prior steps. Each file must contain:

1. a one-line context describing what Step `NN` implemented;
2. at least one role-appropriate technical/design question;
3. a concrete answer grounded in the code and design actually implemented in Step `NN`;
4. a critique covering what is good, what is weak or missing, and how the answer could be stronger.

The four questions must not merely repeat the same question with different job titles. Choose concerns appropriate to the level and to the actual step. Useful dimensions include implementation correctness and maintainability, architecture and scaling tradeoffs, operational/product implications, organizational or roadmap decisions, measurement semantics, security, reliability, and cost where relevant.

Keep the material concise and useful for technical interview practice. Do not invent complexity that the step did not implement.

Update the design-question index if the repository has one.

The step's `prompts/NNN-output.md` must still contain its concise Design Q&A / design-decision summary; the role-specific files are additional learning material.

Before completing the step, verify all four role files exist and are grounded in the final implementation.