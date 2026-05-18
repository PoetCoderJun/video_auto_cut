# Contributing

Contributions should stay inside the public core boundary:

- algorithm modules under `video_auto_cut/`;
- direct prompt contracts under `skills/direct-prompts/`;
- small text fixtures and non-networked tests;
- public documentation.

Do not submit production secrets, customer data, database replicas, generated media, browser profiles, payment code, hosted-service deployment scripts, analytics IDs, or private operations runbooks.

By submitting a contribution, you confirm that you have the right to submit it and that it is licensed under the same non-commercial license as this repository unless a separate written agreement says otherwise.

Before opening a change, run:

```bash
python -m unittest discover tests -p "test_*.py" -v
```
