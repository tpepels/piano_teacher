# Local piano fingering runtime

## Lumikey package and pretrained models

`@lumikey/piano-fingering-model` **0.3.0**, published by the Lumikey project:
https://github.com/lumikey/piano-fingering-model/tree/e03c0da6bfe6b4299dbdacb421bd5792f1721631/js

The published npm artifact declares **MIT** in its `package.json`. Its published
files include the supported JavaScript inference implementation and both
pretrained ONNX models. There is no separate model license, copyright notice,
LICENSE or NOTICE file in that artifact (or the inspected upstream checkout).
We retain the artifact unchanged via npm, including its README and license
metadata; the lockfile records its exact integrity. This integration relies on
the publisher's MIT declaration for that complete package, including its models.
It does not copy the separately published Python source or training data.

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

`onnxruntime-node` and `onnxruntime-common` **1.30.0**.
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

Transitive dependency notices remain in the installed npm packages. Keep their
complete package directories and this file if distributing an installed runtime.
