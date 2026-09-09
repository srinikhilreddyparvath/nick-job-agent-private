# Third-Party Notices

RoleCall includes open-source dependencies distributed under their respective licenses. Dependency names and exact versions are recorded in `backend/requirements.txt` and `frontend/package-lock.json`; their license terms remain with those components.

## Career-Ops provider implementations

The RoleCall BambooHR, Recruitee, Teamtailor, and Workable public job-source connectors are Python adaptations of provider behavior and parsing rules from Career-Ops:

- `providers/bamboohr.mjs` → `backend/app/connectors/bamboohr.py`
- `providers/recruitee.mjs` → `backend/app/connectors/recruitee.py`
- `providers/teamtailor.mjs` → `backend/app/connectors/teamtailor.py`
- `providers/workable.mjs` → `backend/app/connectors/workable.py`

Career-Ops is Copyright (c) 2026 Santiago Fernández de Valderrama and is used under the MIT License:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

RoleCall's Doctor, external-content boundary, and source-health architecture were independently reimplemented for RoleCall rather than copied.

If code is copied or substantially adapted in the future, its copyright and permission notices must be added here and, where appropriate, to the affected source file before distribution.
