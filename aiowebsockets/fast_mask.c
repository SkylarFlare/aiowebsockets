#include <Python.h>

static const Py_ssize_t EXPECTED_MASK_LEN = 4;

static PyObject *
fast_mask(PyObject *self, PyObject *args)
{
    PyObject *input, *mask, *result;
    Py_ssize_t input_len, mask_len, i = 0;
    char *input_charmap, *result_charmap, *mask_charmap;
    
    if(!PyArg_ParseTuple(args, "YY", &input, &mask)) {
        return NULL;
    }
    
    // Grab and verify mask length
    mask_len = PyByteArray_Size(mask);
    
    if(mask_len != EXPECTED_MASK_LEN) {
        return NULL;
    }
    
    // Buffers
    input_len = PyByteArray_Size(input);
    input_charmap = PyByteArray_AsString(input);
    mask_charmap = PyByteArray_AsString(mask);
    result = PyByteArray_FromStringAndSize(NULL, input_len);
    result_charmap = PyByteArray_AsString(result);
    
    // XoR
    for(; i < input_len; i++) {
        result_charmap[i] = input_charmap[i] ^ mask_charmap[i & (mask_len - 1)];
    }
    
    return result;
}

static PyMethodDef xor_methods[] = {
    {
        "fast_mask",
        (PyCFunction) fast_mask,
        METH_VARARGS | METH_KEYWORDS,
        "Apply masking to websocket data frames.",
    },
    {NULL, NULL, 0, NULL},      /* Sentinel */
};

static struct PyModuleDef fast_mask_module = {
    PyModuleDef_HEAD_INIT,
    "aiowebsockets.fast_mask", /* name of module */
    "C implementation of XoR.", /* module documentation */
    -1, /* size of sate of module, may be -1 */
    xor_methods, /* Module Methods Export */
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit_fast_mask(void)
{
    return PyModule_Create(&fast_mask_module);
}

