# Local piano fingering runtime

## Lumikey package and pretrained models

`@lumikey/piano-fingering-model` **0.3.0**, published by the Lumikey project:
https://github.com/lumikey/piano-fingering-model/tree/e03c0da6bfe6b4299dbdacb421bd5792f1721631/js

The published npm artifact declares **MIT** in its `package.json` and contains
the JavaScript inference implementation and both pretrained ONNX models.
Piano Teacher ports the published tokenization and inference to Python and
ships the two model files byte for byte. There is no separate model license,
copyright notice, LICENSE or NOTICE file in the inspected upstream artifact
or checkout. The publisher's MIT declaration for the artifact is the basis
for this use of its inference logic and weights.

The upstream training code loads a PIG fingering dataset for each hand. The
dataset publishers describe nonprofit academic use and request citation of
Eita Nakamura, Yasuyuki Saito and Kazuyoshi Yoshii, “Statistical Learning and
Estimation of Piano Fingering,” Information Sciences 517 (2020), 68–85.
Piano Teacher distributes the exported weights and inference code. The
publication terms for the data and the MIT declaration for the npm package
leave commercial rights for the resulting weights unresolved in this audit.
[Upstream training code](https://github.com/lumikey/piano-fingering-model/blob/e03c0da6bfe6b4299dbdacb421bd5792f1721631/python/train.py#L74) · [Dataset publisher and terms](https://beam.kisarazu.ac.jp/saito/research/PianoFingeringDataset/)

Registry metadata for the exact artifact:
https://registry.npmjs.org/@lumikey%2Fpiano-fingering-model/0.3.0

Package tarball SHA-1: `40c99fbfd228f81e00d765438119de0795a2b58f`.

Model SHA-256 (also checked before every inference):

- Left: `246f2fed013c27ca8c32ce9d070002afcc49da4f1dfb0c43e09a4a3f9f2fb86e`
- Right: `f931288302b87f5eec1c8af29a570ee0213a272a13eeb590991a285e1f1b67eb`

The MIT permission terms associated with the package's declared SPDX identifier:

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

No missing Lumikey copyright statement has been invented here.

## ONNX Runtime

`onnxruntime` **1.30.0** (Python, CPU).
https://github.com/microsoft/onnxruntime/tree/v1.30.0

MIT License

Copyright (c) Microsoft Corporation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

The Python runtime distribution includes the wheel's `onnxruntime/LICENSE`
and `onnxruntime/ThirdPartyNotices.txt` with its compiled libraries.
