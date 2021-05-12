import numpy as np
import deeptrack as dt
import StructuralNoise as SN
from scipy.optimize import curve_fit


class SimulateTool():
    def __init__(
            self, numImages=1,
            numParticlesRange=[1, 10],
            limit=10,
            addNoise=True,
            addAugment=True,
            addIllumination=True,
            addStructNoise=True,
            imageSize=[128, 128],
            noiseRange=[50, 60]):
        self.numImages = numImages
        self.positions = []
        self.images = []
        self.IMAGE_X_SIZE = imageSize[0]
        self.IMAGE_Y_SIZE = imageSize[1]
        self.MIN_Z = -30e-6
        self.MAX_Z = 30e-6
        self.Z_SCALE = 1e-7
        self.PIXEL_SCALE = 3.45e-7
        self.numParticlesRange = numParticlesRange
        self.limit = limit
        self.resolution = 1.14e-6
        self.magnification = 10

        pupil = dt.HorizontalComa(
            coefficient=lambda: 0.2 + 0.6 * np.random.rand()) \
            + dt.VerticalComa(
                    coefficient=lambda: 0.2 + 0.6 * np.random.rand())

        particle = dt.MieSphere(
            refractive_index=lambda: np.random.uniform(1.37, 1.7),
            refractive_index_medium=1.33,
            radius=lambda: (1 + np.random.rand()) * 150e-9,
            position=lambda: self.random_position(
                limit=self.limit,
                image_size_x=self.IMAGE_X_SIZE,
                image_size_y=self.IMAGE_Y_SIZE),
            z=lambda: + self.MIN_Z / self.Z_SCALE
                      + (np.random.rand()
                         * (self.MAX_Z / self.Z_SCALE
                            - self.MIN_Z / self.Z_SCALE)),
            position_unit="pixel",
            wavelength=633e-9,
            #L=5
        )

        if addIllumination:
            illumination_gradient = dt.IlluminationGradient(
                gradient=lambda: (np.random.randn(2)) * 5e-7)
        else:
            illumination_gradient = dt.IlluminationGradient(
                gradient=[0, 0])

        sigma_max = 0
        if addNoise:
            sigma_max = 5e-2
        noise_real = dt.Gaussian(
            mu=0,
            sigma=lambda: np.random.rand(1) * sigma_max)
        noise_imaginary = dt.Gaussian(
            mu=0,
            sigma=lambda: np.random.rand(1) * 1j * sigma_max)

        brightfield_microscope = dt.Brightfield(
            NA=1.3,
            aperature_angle=53.7 * 2 * np.pi / 360,
            resolution=self.resolution,
            magnification=self.magnification,
            illumination=illumination_gradient + noise_real + noise_imaginary,
            wavelength=633e-9,
            output_region=(0, 0, self.IMAGE_X_SIZE, self.IMAGE_Y_SIZE),
            upscale=1,
            return_field=True,
            pupil=pupil,
            padding=(10,) * 4,
        )

        feature = brightfield_microscope(
            lambda: particle ** np.random.randint(
                self.numParticlesRange[0], self.numParticlesRange[1] + 1))

        if addAugment:
            feature = dt.FlipUD(dt.FlipLR(feature))

        for i in range(0, numImages):
            feature.update()
            resolved_output = feature.resolve()

            if addStructNoise:
                self.makeStructNoise(resolved_output)

                resolved_output = np.squeeze(resolved_output) + self.struc_noise

            self.images.append(resolved_output)

        self.feature = feature

    def makeStructNoise(self, image):
        ''' Generates new structural noise and saves it in a class variable '''
        self.struc_noise = SN.struc_image(
            image.shape[1],
            image.shape[0],
            np.max(image)/70)

    def getStructNoise(self):
        ''' Returns the structura noise class variable '''
        return self.struc_noise

    # Retunerar arrayen med bilderna.
    def getImages(self):
        ''' Returns the array of generated images '''
        return self.images

    # Could probably be removed, serves really no purpose atm.
    def getImageAmplitude(self, image):
        ''' Returns the amplitude of the given image. Same as
            np.abs(image). '''
        return np.abs(image)

    def getMaxImageAmplitude(self, image):
        ''' Returns the maximum amplitud of an image '''
        max = 0
        for k in range(self.numImages):
            MaxImageK = np.max(self.getImageAmplitude(image[k]))
            if MaxImageK > max:
                max = MaxImageK
        return max

    def getRefractiveIndex(self, image):
        ''' ??? '''
        return image.properties[0]['refractive_index']

    def getIllumination(self, image):
        ''' Returns the illumination gradient of the given image '''
        return image.properties[0]['illumination'].gradient.current_value

    def getNewImage(self):
        ''' Generates and returns a new complex image '''
        old_positions = self.positions
        self.positions = []
        self.feature.update()
        image = self.feature.resolve()
        if self.positions == []:
            self.positions = old_positions
        return image

    # Retunerar feature:n som ansvarar för bild-genereringen. Lämpligt vid
    # användning av Deeptracks generators.
    def getSimulationFeature(self):
        ''' Returns the deeptrack feature responsible for generating images '''
        return self.feature

    def getResolvedProperties(self):
        ''' Returns the resolved class image variable '''
        a = self.feature
        return a.resolve().properties

    def getNoise(self, image, snr=1):
        ''' DEPRECIATED: Returns manually calculated noise. Not needed atm. '''
        image[image < 0] = 0

        peak = np.abs(np.max(image))

        rescale = snr ** 2 / peak ** 2

        noisy_image = dt.Image(np.random.poisson(image * rescale) / rescale)
        noisy_image.properties = image.properties

        return noisy_image

    def find_peak_width(self, output_image, number_of_peaks=4,
                        check_length=40) -> list:
        widths = []
        image = np.squeeze(output_image)
        image_size = self.IMAGE_X_SIZE
        positions = self.get_pos(output_image)

        def sine_fit(x, amp_offset, amp, k, phase):
            return amp_offset + amp * np.sin(2 * np.pi * k * x + phase)

        for pos in positions:
            x_pos = int(pos[0])
            y_pos = int(pos[1])

            if x_pos > image_size / 2:
                image_x = image[(x_pos - check_length):x_pos, y_pos]
            else:
                image_x = image[x_pos:(x_pos + check_length), y_pos]
            if y_pos > image_size / 2:
                image_y = image[x_pos, (y_pos - check_length):y_pos]
            else:
                image_y = image[x_pos, y_pos:(y_pos + check_length)]

            image_average = (image_y + image_x) / 2

            init_vals = [1, 0.1, 0.25, 0]  # for [amp_offset, amp, k, phase]
            bounds = ([0.8, 0.01, 0.1, -np.pi], [1.2, 0.2, 0.5, np.pi])
            try:
                best_vals, covar = curve_fit(sine_fit, np.arange(check_length),
                                             image_average, p0=init_vals,
                                             bounds=bounds)
            except RuntimeError:
                widths.append(32)
                continue
            widths.append(number_of_peaks * 2 / best_vals[2])
        return widths

    def random_position(self, limit, image_size_x, image_size_y):
        ''' Generates a new position with a distance above specified limit
            to all other particles in the class position array.
            Should probably be private. '''
        good = False
        i = 0
        while not good:
            newpos = np.random.rand(2) * (image_size_x, image_size_y)
            good = True
            for pos in self.positions:
                distance = np.linalg.norm(newpos - pos)
                if distance < limit:
                    good = False
            i += 1
            if i > 100:
                print("WARNING: Could not add particle with specified limit, "
                      "please decrease limit or number of particles. "
                      "Adding randomly...")
                return np.random.rand(2) * (image_size_x, image_size_y)

        self.positions.append(newpos)
        return newpos

    def get_pos(self, resolved_image):
        v = []
        for properties in resolved_image.properties:
            if "position" in properties:
                v = np.append(v, properties["position"])
        s = np.shape(v)
        v = np.reshape(v, (int(s[0] / 2), 2))
        return v

    def get_physical_position(self, x, y, z):
        ''' Returns the actual physical position expressed in meters.
            Return value is a list formated as [x, y, z]. '''
        return [x * self.IMAGE_X_SIZE * self.resolution / self.magnification,
                y * self.IMAGE_Y_SIZE * self.resolution / self.magnification,
                z * self.resolution / self.magnification]

    def get_all_pos(self, resolved_image):
        ''' Returns an array of properties for each particle in the resolved
            image. Returns [[particle 1 prop.], [particle 2 prop.], ...] '''
        v = []
        for properties in resolved_image.properties:
            if "position" in properties:
                tempPos = properties["position"]
                # v = np.append(v, properties["position"] / self.IMAGE_X_SIZE)
                v = np.append(v, [tempPos[0] / self.IMAGE_X_SIZE,
                                  tempPos[1] / self.IMAGE_Y_SIZE])
                v = np.append(v, properties["z"])
                v = np.append(v, properties["radius"])
                v = np.append(v, properties['refractive_index'])
        s = np.shape(v)

        v = np.reshape(v, (int(s[0] / 5), 5))
        return v

    def get_label(self, resolved_image):
        label = []
        positions = self.get_all_pos(resolved_image)
        widths = self.find_peak_width(resolved_image)
        for i in range(np.size(widths)):
            label.append([0,
                          positions[i][0] / self.IMAGE_X_SIZE,
                          positions[i][1] / self.IMAGE_Y_SIZE,
                          positions[i][2],
                          positions[i][3],
                          widths[i] / self.IMAGE_X_SIZE,
                          widths[i] / self.IMAGE_Y_SIZE])
        return label
