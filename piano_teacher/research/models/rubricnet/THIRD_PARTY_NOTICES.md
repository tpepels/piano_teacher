# RubricNet third-party model attribution

The five `fold_*.json` files in this directory are parameter/scaler
conversions of the **actual camera-ready trained weights** from:

P. Ramoneda, V. Eremenko, A. D'Hooge, E. Parada-Cabaleiro and X. Serra,
“Towards Explainable and Interpretable Musical Difficulty Estimation: A
parameter-efficient approach,” ISMIR 2024.

Official source: https://github.com/PRamoneda/rubricnet
Upstream commit: `3ff4a9342948b9588541a2a8524eab68045f6001`
Upstream license: MIT, copyright (c) 2025 Pedro.

The model parameters have been transformed into inert JSON; the source Git
blob hashes of the original scaler and checkpoint are embedded in each file.
The original upstream implementation and data are NOT copied into this
directory. The no-PyTorch mathematical implementation is in
`piano_teacher/research/rubricnet_core.py`.

MIT License

Copyright (c) 2025 Pedro

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
