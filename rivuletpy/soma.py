# -*- coding: utf-8 -*-
from .utils.io import writetiff3d

"""
somasnakes
===========
The original package is adjusted for soma detection by donghao zhang and siqi liu.

This soma submodule can be used for soma detection only, but this submodule is
currently embedded in rivuletpy. The soma mask can be generate by setting
its corresponding argument. The soma detection requires an initial soma centroid, 
estimated somatic radius and grayscale neuron image. Soma growth is based on the 
Morphological Active Contours without Edges algorithm.  The original paper is named as
A morphological approach to curvature-based evolution of curves and surfaces.
The following papers are Rivulet papers. The soma growth algorithm can converge by
applying the sliding window technique. 
Journal Rivulet Paper : Rivulet: 3D Neuron Morphology Tracing with Iterative Back-Tracking
Conference Rivulet Paper : Reconstruction of 3D neuron morphology using Rivulet back-tracking
soma is a submodule of rivuletpy
"""

__author__ = "Donghao Zhang <zdhpeter1991@gmail.com>, Siqi Liu <lsqshr@gmail.com>"

from itertools import cycle

import numpy as np
from scipy import ndimage
from scipy.ndimage import binary_dilation, binary_erosion, \
                        gaussian_filter, gaussian_gradient_magnitude

class fcycle(object):
    
    def __init__(self, iterable):
        """Call functions from the iterable each time it is called."""
        self.funcs = cycle(iterable)

    
    def __call__(self, *args, **kwargs):
        f = next(self.funcs)
        return f(*args, **kwargs)
    

# SI and IS operators for 2D and 3D.
_P2 = [np.eye(3), np.array([[0,1,0]]*3), np.flipud(np.eye(3)), np.rot90([[0,1,0]]*3)]
_P3 = [np.zeros((3,3,3)) for i in range(9)]

_P3[0][:,:,1] = 1
_P3[1][:,1,:] = 1
_P3[2][1,:,:] = 1
_P3[3][:,[0,1,2],[0,1,2]] = 1
_P3[4][:,[0,1,2],[2,1,0]] = 1
_P3[5][[0,1,2],:,[0,1,2]] = 1
_P3[6][[0,1,2],:,[2,1,0]] = 1
_P3[7][[0,1,2],[0,1,2],:] = 1
_P3[8][[0,1,2],[2,1,0],:] = 1

_aux = np.zeros((0))

def SI(u):
    """SI operator."""
    global _aux
    if np.ndim(u) == 2:
        P = _P2
    elif np.ndim(u) == 3:
        P = _P3
    else:
        raise ValueError("u has an invalid number of dimensions (should be 2 or 3)")
    
    if u.shape != _aux.shape[1:]:
        _aux = np.zeros((len(P),) + u.shape)
    
    for i in range(len(P)):
        _aux[i] = binary_erosion(u, P[i])
    
    return _aux.max(0)


def circle_levelset(shape, center, sqradius, scalerow=1.0):
    """Build a binary function with a circle as the 0.5-levelset."""
    grid = np.mgrid[list(map(slice, shape))].T - center
    phi = sqradius - np.sqrt(np.sum((grid.T)**2, 0))
    u = np.float_(phi > 0)
    return u


def IS(u):
    """IS operator."""
    global _aux
    if np.ndim(u) == 2:
        P = _P2
    elif np.ndim(u) == 3:
        P = _P3
    else:
        raise ValueError("u has an invalid number of dimensions (should be 2 or 3)")
    
    if u.shape != _aux.shape[1:]:
        _aux = np.zeros((len(P),) + u.shape)
    
    for i in range(len(P)):
        _aux[i] = binary_dilation(u, P[i])
    
    return _aux.min(0)

# SIoIS operator.
SIoIS = lambda u: SI(IS(u))
ISoSI = lambda u: IS(SI(u))
curvop = fcycle([SIoIS, ISoSI])

# Stopping factors (function g(I) in the paper).
def gborders(img, alpha=1.0, sigma=1.0):
    """Stopping criterion for image borders."""
    
    # The norm of the gradient.
    gradnorm = gaussian_gradient_magnitude(img, sigma, mode='constant')
    return 1.0/np.sqrt(1.0 + alpha*gradnorm)


def glines(img, sigma=1.0):
    """Stopping criterion for image black lines."""
    return gaussian_filter(img, sigma)


class MorphACWE(object):
    """Morphological ACWE based on the Chan-Vese energy functional."""
    
    def __init__(self, data, smoothing=1, lambda1=1, lambda2=1):
        """Create a Morphological ACWE solver.
        
        Parameters
        ----------
        data : ndarray
            The image data.
        smoothing : scalar
            The number of repetitions of the smoothing step (the
            curv operator) in each iteration. In other terms,
            this is the strength of the smoothing. This is the
            parameter µ.
        lambda1, lambda2 : scalars
            Relative importance of the inside pixels (lambda1)
            against the outside pixels (lambda2).
        """
        self._u = None
        self.smoothing = smoothing
        self.lambda1 = lambda1
        self.lambda2 = lambda2        
        self.data = data
 

    def set_levelset(self, u):
        self._u = np.double(u)
        self._u[u>0] = 1
        self._u[u<=0] = 0
    

    levelset = property(lambda self: self._u,
                        set_levelset,
                        doc="The level set embedding function (u).")
    

    def step(self):
        """Perform a single step of the morphological Chan-Vese evolution."""
        # Assign attributes to local variables for convenience.
        # print('The step function of MorphACWE class has been called')
        u = self._u
        
        if u is None:
            raise ValueError("the levelset function is not set (use set_levelset)")
        
        data = self.data
        
        # Determine c0 and c1.
        inside = u>0
        outside = u<=0
        c0 = data[outside].sum() / float(outside.sum())
        c1 = data[inside].sum() / float(inside.sum())
        
        # Image attachment.
        dres = np.array(np.gradient(u))
        abs_dres = np.abs(dres).sum(0)
        #aux = abs_dres * (c0 - c1) * (c0 + c1 - 2*data)
        aux = abs_dres * (self.lambda1*(data - c1)**2 - self.lambda2*(data - c0)**2)
        
        res = np.copy(u)
        res[aux < 0] = 1
        res[aux > 0] = 0
        
        # Smoothing.
        for i in range(self.smoothing):
            res = curvop(res)
        self._u = res
    
    
    def run(self, iterations):
        """Run several iterations of the morphological Chan-Vese method."""
        for i in range(iterations):
            self.step()
    

    def autoconvg(self):
        """Soma detection converges by itself."""
        
        # Autoconvg is the abbreviation of automatic convergence
        iterations = 200
        
        # The following vector is used for storing values of the number of foreground voxels 
        foreground_num = np.zeros(iterations)
        
        # The following vector is initialised for storing forward difference
        forward_diff_store = np.zeros(iterations)
        
        # This is the initilization of automatic converge
        for i in range(iterations):
            self.step()
            u = self._u
            volu = sum(u[u>0])
            foreground_num[i] = volu
            if i > 0:
                # The variable diff_step is the current first order difference 
                diff_step = foreground_num[i] - foreground_num[i-1]
                forward_diff_store[i-1] = diff_step
                if i > 6:
                    # The variable cur_slider_diff is the sum of sliding window
                    # The size of sliding window is 6
                    cur_slider_diff = np.sum(forward_diff_store[i-6:i-1])
                    if np.absolute(cur_slider_diff) < 20 | \
                     (np.absolute(cur_slider_diff) < (0.1*foreground_num[i])):
                        print('Perform the automatic converge')
                        break


class MorphGAC(object):
    """Morphological GAC based on the Geodesic Active Contours."""
    
    def __init__(self, data, smoothing=1, threshold=0, balloon=0):
        """Create a Morphological GAC solver.
        
        Parameters
        ----------
        data : array-like
            The stopping criterion g(I). See functions gborders and glines.
        smoothing : scalar
            The number of repetitions of the smoothing step in each
            iteration. This is the parameter µ.
        threshold : scalar
            The threshold that determines which areas are affected
            by the morphological balloon. This is the parameter θ.
        balloon : scalar
            The strength of the morphological balloon. This is the parameter ν.
        """
        self._u = None
        self._v = balloon
        self._theta = threshold
        self.smoothing = smoothing        
        self.set_data(data)
    

    def set_levelset(self, u):
        self._u = np.double(u)
        self._u[u>0] = 1
        self._u[u<=0] = 0
    

    def set_balloon(self, v):
        self._v = v
        self._update_mask()
    
    
    def set_threshold(self, theta):
        self._theta = theta
        self._update_mask()
    

    def set_data(self, data):
        self._data = data
        self._ddata = np.gradient(data)
        self._update_mask()
        
        # The structure element for binary dilation and erosion.
        self.structure = np.ones((3,)*np.ndim(data))
    
    
    def _update_mask(self):
        """Pre-compute masks for speed."""
        self._threshold_mask = self._data > self._theta
        self._threshold_mask_v = self._data > self._theta/np.abs(self._v)
    
    levelset = property(lambda self: self._u,
                        set_levelset,
                        doc="The level set embedding function (u).")
    
    data = property(lambda self: self._data,
                        set_data,
                        doc="The data that controls the snake evolution (the image or g(I)).")
    
    balloon = property(lambda self: self._v,
                        set_balloon,
                        doc="The morphological balloon parameter (ν (nu, not v)).")
    
    threshold = property(lambda self: self._theta,
                        set_threshold,
                        doc="The threshold value (θ).")
    
    
    def step(self):
        """Perform a single step of the morphological snake evolution."""
        # Assign attributes to local variables for convenience.
        u = self._u
        gI = self._data
        dgI = self._ddata
        theta = self._theta
        v = self._v
        
        if u is None:
            raise ValueError("the levelset is not set (use set_levelset)")
        
        res = np.copy(u)
        
        # Balloon.
        if v > 0:
            aux = binary_dilation(u, self.structure)
        elif v < 0:
            aux = binary_erosion(u, self.structure)
        if v!= 0:
            res[self._threshold_mask_v] = aux[self._threshold_mask_v]
        
        # Image attachment.
        aux = np.zeros_like(res)
        dres = np.gradient(res)
        for el1, el2 in zip(dgI, dres):
            aux += el1*el2
        res[aux > 0] = 1
        res[aux < 0] = 0
        
        # Smoothing.
        for i in range(self.smoothing):
            res = curvop(res)
        
        self._u = res
    
    
    def run(self, iterations):
        """Run several iterations of the morphological snakes method."""
        for i in range(iterations):
            self.step()
    

def evolve_visual(msnake, levelset=None, num_iters=20, background=None):
    """
    Visual evolution of a morphological snake.
    
    Parameters
    ----------
    msnake : MorphGAC or MorphACWE instance
        The morphological snake solver.
    levelset : array-like, optional
        If given, the levelset of the solver is initialized to this. If not
        given, the evolution will use the levelset already set in msnake.
    num_iters : int, optional
        The number of iterations.
    background : array-like, optional
        If given, background will be shown behind the contours instead of
        msnake.data.
    """
    from matplotlib import pyplot as ppl
    
    if levelset is not None:
        msnake.levelset = levelset
    
    # Prepare the visual environment.
    fig = ppl.gcf()
    fig.clf()
    ax1 = fig.add_subplot(1,2,1)
    if background is None:
        ax1.imshow(msnake.data, cmap=ppl.cm.gray)
    else:
        ax1.imshow(background, cmap=ppl.cm.gray)
    ax1.contour(msnake.levelset, [0.5], colors='r')    
    ax2 = fig.add_subplot(1,2,2)
    ax_u = ax2.imshow(msnake.levelset)
    ppl.pause(0.001)
    
    # Iterate.
    for i in range(num_iters):
        
        # Evolve.
        msnake.step()
        
        # Update figure.
        del ax1.collections[0]
        ax1.contour(msnake.levelset, [0.5], colors='r')
        ax_u.set_data(msnake.levelset)
        fig.canvas.draw()
        #ppl.pause(0.001)
    
    # Return the last levelset.
    return msnake.levelset


def evolve_visual3d(msnake, levelset=None, num_iters=20):
    """
    Visual evolution of a three-dimensional morphological snake.
    
    Parameters
    ----------
    msnake : MorphGAC or MorphACWE instance
        The morphological snake solver.
    levelset : array-like, optional
        If given, the levelset of the solver is initialized to this. If not
        given, the evolution will use the levelset already set in msnake.
    num_iters : int, optional
        The number of iterations.
    """
    from mayavi import mlab
    import matplotlib.pyplot as ppl
    
    if levelset is not None:
        msnake.levelset = levelset
    
    fig = mlab.gcf()
    mlab.clf()
    src = mlab.pipeline.scalar_field(msnake.data)
    mlab.pipeline.image_plane_widget(src, plane_orientation='x_axes', colormap='gray')
    cnt = mlab.contour3d(msnake.levelset, contours=[0.5])
    
    @mlab.animate(ui=True)
    def anim():
        for i in range(num_iters):
            msnake.step()
            cnt.mlab_source.scalars = msnake.levelset
            print("Iteration %s/%s..." % (i + 1, num_iters))
            yield
    
    anim()
    mlab.show()
    
    # Return the last levelset.
    return msnake.levelset


def soma_detect(img, somapos, somaradius, smoothing, lambda1, lambda2, soma, iterations):
    """
    Automatic detection of soma volume.

    Parameters
    ----------
    img : grayscale neuron image.
        the type of neuron image is numpy uint8
        the dimension of neuron image is 3 
        the neuron image is array-like
    somaradius : the approximate value of soma radius estimated from distance transform
        the type of somaradius is float64
        somaradius is just a float number
    somapos : the coordinate of estimated soma centroid 
        the type of somapos is int64
        the shape of somapos is (3,)
        somapos is array-like
    soma_lambda1 : a float number controls the weight of internal energy
    soma_lambda2 : a float number controls the weight of external energy
    soma : a logic value determines using automatic converge criteria to iterate or not
    iterations : manually set the number of iterations required for the soma
        the type of iterations is int
    """
    ratioxz = img.shape[0] / img.shape[2]
    ratioyz = img.shape[1] / img.shape[2]
    print('The ratioxz is ', ratioxz, 'The ratioyz is ', ratioyz)
    sqrval = (somaradius**0.5 * max(ratioxz, ratioyz))
    sqrval = np.floor(min(max(sqrval, 3), (somaradius**0.5)*6))
    print('The replacesqrval is ', sqrval)
    startpt = somapos - 3 * sqrval
    endpt = somapos + 3 * sqrval
    print(startpt, endpt)

    # # To constrain the soma growth region inside the cubic region
    # # Python index start from 0 
    startpt[0] = min(max(0, startpt[0]), img.shape[0]-1)
    startpt[1] = min(max(0, startpt[1]), img.shape[1]-1)
    startpt[2] = min(max(0, startpt[2]), img.shape[2]-1)

    endpt[0] = min(max(0, endpt[0]), img.shape[0]-1)
    endpt[1] = min(max(0, endpt[1]), img.shape[1]-1)
    endpt[2] = min(max(0, endpt[2]), img.shape[2]-1)
    startpt = startpt.astype(int) # Convert type to int for indexing 
    endpt = endpt.astype(int)
    print(startpt, endpt)
    
    # # Extract soma region for fast soma detection
    somaimg = img[startpt[0]:endpt[0], startpt[1]:endpt[1], startpt[2]:endpt[2]]
    writetiff3d('/home/donghao/Desktop/zebrafishlarveRGC/2_somabox.tif', somaimg)
    centerpt = np.zeros(3)
    centerpt[0] = somaimg.shape[0] / 2
    centerpt[1] = somaimg.shape[1] / 2
    centerpt[2] = somaimg.shape[2] / 2
    centerpt = np.floor(centerpt)
    print(centerpt)
    
    # Morphological ACWE. Initialization of the level-set.
    macwe = MorphACWE(somaimg, smoothing, lambda1, lambda2)
    macwe.levelset = circle_levelset(somaimg.shape, np.floor(centerpt), sqrval)
    if iterations == -1:
        macwe.autoconvg() # automatic soma detection
    else:        
        # Input the iteration number manually
        for i in range(iterations):
            macwe.step()
    
    # Initialise soma mask image 
    fullsomaimg = np.zeros((img.shape[0], img.shape[1], img.shape[2]))
    
    # The soma mask image contains only two possible values so each element is either 0 or 40
    fullsomaimg[startpt[0]:endpt[0], startpt[1]:endpt[1], startpt[2]:endpt[2]] = macwe._u * 40
    fullsomaimg.astype(int)
    
    # Convert to uint8 so the soma mask image can be saved
    fullsomaimg = fullsomaimg.astype(np.uint8)
    return fullsomaimg
