# This is the equivalent of daxgen.py in the pegasus examples

# Notes: 
# 1. I don't understand the different link types (register, transfer).
#    This must depend on how the larger inputs get to the job.
# 2. As far as I can tell pegasus will put everything in /scratch in the container.
#   Need to figure out how to deal with this.
# 3. Do we need to write generate_replica_catalog method?  I don't know how that works.



from .launcher import Launcher
import os





container_transformation_entry = """

tr {stage_name} {{
    site condorpool {{

        pfn "/opt/desc/run.py"
        arch "x86_64"
        os "linux"

        # Can use this to signal to the runtime to 
        # do things a bit differently
        profile env "DESC_PEGAUSUS_INPUTS"

        # The path is in the container
        type "INSTALLED"

        # Use the container defined below
        container {stage_name}_container
    }}
}}

cont {stage_name}_container {{
     # can be either docker or singularity
     type "docker"

     # URL to image in a docker|singularity hub OR
     # URL to an existing docker image exported as a tar file or singularity image
     image "docker:///{image_name}" 
}}

"""

class PegasusLauncher(Launcher):
    def generate_transformation_catalog(self, tc_name):
        tc = open(tc_name, "w")
        for stage_name, stage_class in self.pipeline.sequence():
            image_name = self.pipeline.image_name(stage_name)
            text = container_transformation_entry.format(stage_name=stage_name, image_name=image_name)
            tc.write(text)
        tc.close()


    def generate_dax(self, daxfile):
        from Pegasus.DAX3 import ADAG, Job, File, Link

        # The DAX generator
        dax = ADAG("pipeline")

        # Some bits of metadata.  Shoulf put plenty more here.
        dax.metadata("owner", self.pipeline.owner)
        dax.metadata("basename", self.pipeline.basename)
        dax.metadata("version", self.pipeline.version)

        # string tag -> pegasus File object mapping of all the 
        # inputs and outputs used by any pipeline stage.
        files = {}

        # First generate the overall inputs to the pipeline, 
        # i.e. ones that are not generated by any other stage
        # but must be specified at the start
        for tag in self.pipeline.input_tags():
            path = self.info['inputs'].get(tag)
            files[tag] = File(path)

        # Now go through the pipeline in sequence.
        for stage_name, stage_class in self.pipeline.sequence():
            # The stage in the pipeline.  We describe the meaning of it
            # (which image it corresponds to)
            # in the transformation catalog generation
            job = Job(stage_name, id=stage_name)

            # Configuration files for this job.
            # These will not be built during the pipeline and must be 
            # provided by the user
            for config_tag, config_filename in stage_class.config.items():
                filename = self.pipeline.cfg[stage_name]['config'][config_tag]
                config_path = os.path.join(self.config_dir(), filename)
                config = File(config_path)
                job.uses(config, link=Link.INPUT)

            # Input files for the job, either created by the user or by previous
            # stages.  In either case they should be in the "files" dictionary, because
            # precursor jobs will have been added before this one.
            for input_tag in stage_class.inputs.keys():
                job.uses(files[input_tag], link=Link.INPUT)


            # Output files from the job. These will be created by the job
            # and used by future jobs
            for output_tag, output_type in stage_class.outputs.items():
                output_filename = "{}.{}".format(output_tag, output_type)
                output = File(output_filename)
                job.uses(output, link=Link.OUTPUT, transfer=True, register=True)
                files[output_tag] = output

            # Add this job to the pipeline
            dax.addJob(job)

            # Tell pegasus which jobs this one depends on.
            # The pipeline already knows this information.
            # The pipeline.sequence command runs through
            # the jobs in an order that guarantees that a job's predecessors are 
            # always done before it is, so they will always exist in the dax by this point.
            for predecessor_name in self.pipeline.dependencies(stage_name):
                dax.depends(stage_name, predecessor_name)

        # Generate the final DAX XML file.
        dax.writeXML(open(daxfile, "w"))

    def generate_replica_catalog(self):
        pass

    def generate(self, daxfile, tcfile):
        self.generate_transformation_catalog(tcfile)
        self.generate_dax(daxfile)
