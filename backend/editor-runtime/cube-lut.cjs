// Convert the editor's numeric LUT to a job-local .cube file. No client paths
// or LUT header text are executed or forwarded to FFmpeg.
const fs = require('node:fs');
const path = require('node:path');

function writeCubeLut(lut, target) {
    const size = Number(lut?.size);
    const is3d = lut?.is3d !== false;
    if (!Number.isInteger(size) || size < 2 || size > (is3d ? 65 : 65536)) {
        throw new Error('Custom LUT size must be 2–65 for 3D or 2–65536 for 1D.');
    }
    const count = 3 * (is3d ? size ** 3 : size);
    const values = lut.data?.__rayflowTypedArray ? lut.data.values : lut.data;
    if (!values || Object.keys(values).length !== count) throw new Error('The custom LUT has incomplete sample data.');
    const numeric = value => {
        if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('The custom LUT contains an invalid number.');
        return value;
    };
    const min = lut.domainMin || [0, 0, 0];
    const max = lut.domainMax || [1, 1, 1];
    if (min.length !== 3 || max.length !== 3 || min.some((value, i) => numeric(value) >= numeric(max[i]))) {
        throw new Error('The custom LUT has an invalid input domain.');
    }
    const lines = [`${is3d ? 'LUT_3D_SIZE' : 'LUT_1D_SIZE'} ${size}`,
        `DOMAIN_MIN ${min.map(numeric).join(' ')}`, `DOMAIN_MAX ${max.map(numeric).join(' ')}`];
    for (let i = 0; i < count; i += 3) lines.push([0, 1, 2].map(offset => numeric(values[i + offset]).toFixed(8)).join(' '));
    fs.writeFileSync(target, lines.join('\n') + '\n');
    const escaped = path.resolve(target).replaceAll('\\', '/').replaceAll(':', '\\:').replaceAll("'", "'\\''");
    return `${is3d ? 'lut3d' : 'lut1d'}=file='${escaped}':interp=${is3d ? 'trilinear' : 'linear'}`;
}

module.exports = { writeCubeLut };
